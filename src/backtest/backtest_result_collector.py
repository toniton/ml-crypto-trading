from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.trade import Trade
from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.domain.result import (
    BacktestExecutionDiagnostics,
    BacktestFill,
    BacktestResult,
    PortfolioSnapshot,
)
from src.backtest.domain.session import BacktestSession
from src.backtest.events.domain_events import (
    OrderFilledEvent,
    OrderSubmittedEvent,
    PortfolioSnapshotEvent,
)
from src.trading.analytics.trade_attribution_service import TradeAttributionService
from src.trading.events.domain_events import (
    DecisionRejectedEvent,
    DecisionRejectedReason,
    MarketDataEvent,
    MarketRegimeObservedEvent,
    SignalGeneratedEvent,
    TradeClosedEvent,
)

EPOCH_MS_THRESHOLD = 100_000_000_000


class BacktestResultCollector:
    """Collects backtest outputs, regime observations, and risk-block diagnostics."""

    def __init__(self, bus: BacktestEventBus):
        self._market_series: list[MarketData] = []
        self._snapshots: list[PortfolioSnapshot] = []
        self._orders: list[Order] = []
        self._fills: list[BacktestFill] = []
        self._trades: list[Trade] = []
        self._total_signals = 0
        self._risk_blocked_signals = 0
        self._risk_block_reasons: Counter[str] = Counter()
        self._regime_counts: Counter[str] = Counter()

        bus.subscribe_callback(MarketDataEvent, self._on_market_data)
        bus.subscribe_callback(PortfolioSnapshotEvent, self._on_snapshot)
        bus.subscribe_callback(OrderSubmittedEvent, self._on_order_submitted)
        bus.subscribe_callback(OrderFilledEvent, self._on_fill)
        bus.subscribe_callback(TradeClosedEvent, self._on_trade_closed)
        bus.subscribe_callback(SignalGeneratedEvent, self._on_signal_generated)
        bus.subscribe_callback(DecisionRejectedEvent, self._on_decision_rejected)
        bus.subscribe_callback(MarketRegimeObservedEvent, self._on_regime_observed)

    def _on_market_data(self, event: MarketDataEvent) -> None:
        self._market_series.append(event.market_data)

    def _on_snapshot(self, event: PortfolioSnapshotEvent) -> None:
        self._snapshots.append(event.snapshot)

    def _on_order_submitted(self, event: OrderSubmittedEvent) -> None:
        self._orders.append(event.order)

    def _on_fill(self, event: OrderFilledEvent) -> None:
        if event.execution is not None:
            self._fills.append(self._to_fill(event.execution))

    def _on_trade_closed(self, event: TradeClosedEvent) -> None:
        self._trades.append(event.trade)

    def _on_signal_generated(self, _event: SignalGeneratedEvent) -> None:
        self._total_signals += 1

    def _on_decision_rejected(self, event: DecisionRejectedEvent) -> None:
        if event.reason != DecisionRejectedReason.RISK_REJECTED.value:
            return
        self._risk_blocked_signals += 1
        raw_reason = str((event.details or {}).get("reason") or "Portfolio risk limit")
        normalized = self._normalize_risk_reason(raw_reason)
        self._risk_block_reasons[normalized] += 1

    def _on_regime_observed(self, event: MarketRegimeObservedEvent) -> None:
        if event.regime:
            self._regime_counts[event.regime] += 1

    def build_result(self, session: BacktestSession) -> BacktestResult:
        request = session.request
        initial_balance = request.initial_balance
        final_balance = self._snapshots[-1].cash if self._snapshots else initial_balance
        final_equity = self._snapshots[-1].equity if self._snapshots else final_balance

        trades = list(self._trades)
        strategy_attribution = TradeAttributionService.attribute_by_strategy(trades)
        commit_attribution = TradeAttributionService.attribute_by_commit(trades)
        regime_attribution = TradeAttributionService.attribute_by_regime(trades)
        diagnostics = self._build_diagnostics()

        return BacktestResult(
            session_id=session.id,
            ticker_symbol=request.ticker_symbol,
            initial_balance=initial_balance,
            final_balance=final_balance,
            final_equity=final_equity,
            execution=request.execution,
            orders=list(self._orders),
            fills=list(self._fills),
            portfolio_snapshots=list(self._snapshots),
            market_series=list(self._market_series),
            trades=trades,
            strategy_attribution=strategy_attribution,
            commit_attribution=commit_attribution,
            regime_attribution=regime_attribution,
            diagnostics=diagnostics,
        )

    def _build_diagnostics(self) -> BacktestExecutionDiagnostics:
        start_at: Optional[str] = None
        end_at: Optional[str] = None
        duration_seconds: Optional[float] = None
        if self._market_series:
            start_ts = self._to_epoch_seconds(self._market_series[0].timestamp)
            end_ts = self._to_epoch_seconds(self._market_series[-1].timestamp)
            start_at = datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat()
            end_at = datetime.fromtimestamp(end_ts, tz=timezone.utc).isoformat()
            duration_seconds = max(0.0, round(end_ts - start_ts, 2))

        return BacktestExecutionDiagnostics(
            dataset_bar_count=len(self._market_series),
            dataset_start_at=start_at,
            dataset_end_at=end_at,
            dataset_duration_seconds=duration_seconds,
            total_signals=self._total_signals,
            risk_blocked_signals=self._risk_blocked_signals,
            risk_block_reasons=dict(self._risk_block_reasons),
            regime_counts=dict(self._regime_counts),
        )

    @staticmethod
    def _to_epoch_seconds(timestamp: int | float) -> float:
        value = float(timestamp)
        return value / 1000.0 if value >= EPOCH_MS_THRESHOLD else value

    _RISK_REASON_PATTERNS: tuple[tuple[str, str], ...] = (
        ("illiquid", "ILLIQUID regime"),
        ("concentration limit", "Asset concentration limit"),
        ("drawdown", "Drawdown guard"),
        ("exposure", "Portfolio exposure limit"),
        ("daily loss", "Daily loss limit"),
    )

    @classmethod
    def _normalize_risk_reason(cls, raw_reason: str) -> str:
        lower = raw_reason.lower()
        for token, label in cls._RISK_REASON_PATTERNS:
            if token in lower:
                return label
        if ":" in raw_reason:
            return raw_reason.split(":", 1)[0].strip()
        return raw_reason.strip() or "Portfolio risk limit"

    @staticmethod
    def _to_fill(result) -> BacktestFill:
        return BacktestFill(
            order_uuid=result.order_uuid,
            ticker_symbol=result.ticker_symbol,
            trade_action=result.trade_action,
            requested_price=result.requested_price,
            market_price=result.market_price,
            execution_price=result.execution_price,
            quantity=result.executed_quantity,
            fee=result.fee,
            slippage_per_unit=result.slippage_per_unit,
            slippage_cost=result.slippage_cost,
            submitted_at=result.submitted_at,
            executed_at=result.executed_at,
        )
