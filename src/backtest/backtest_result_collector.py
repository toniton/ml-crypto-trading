from __future__ import annotations

from api.interfaces.order import Order
from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.domain.result import (
    BacktestFill,
    BacktestResult,
    MarketDataPoint,
    PortfolioSnapshot,
)
from src.backtest.domain.session import BacktestSession
from src.backtest.events.domain_events import (
    MarketDataPointEvent,
    OrderFilledEvent,
    OrderSubmittedEvent,
    PortfolioSnapshotEvent,
)


class BacktestResultCollector:
    def __init__(self, bus: BacktestEventBus):
        self._market_series: list[MarketDataPoint] = []
        self._snapshots: list[PortfolioSnapshot] = []
        self._orders: list[Order] = []
        self._fills: list[BacktestFill] = []

        bus.subscribe_callback(MarketDataPointEvent, self._on_market_data_point)
        bus.subscribe_callback(PortfolioSnapshotEvent, self._on_snapshot)
        bus.subscribe_callback(OrderSubmittedEvent, self._on_order_submitted)
        bus.subscribe_callback(OrderFilledEvent, self._on_fill)

    def _on_market_data_point(self, event: MarketDataPointEvent) -> None:
        self._market_series.append(event.point)

    def _on_snapshot(self, event: PortfolioSnapshotEvent) -> None:
        self._snapshots.append(event.snapshot)

    def _on_order_submitted(self, event: OrderSubmittedEvent) -> None:
        self._orders.append(event.order)

    def _on_fill(self, event: OrderFilledEvent) -> None:
        if event.execution is not None:
            self._fills.append(self._to_fill(event.execution))

    def build_result(self, session: BacktestSession) -> BacktestResult:
        request = session.request
        initial_balance = request.initial_balance
        final_balance = self._snapshots[-1].cash if self._snapshots else initial_balance
        final_equity = self._snapshots[-1].equity if self._snapshots else final_balance

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
        )

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
