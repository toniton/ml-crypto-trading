from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from api.interfaces.trade_action import OrderStatus, TradeAction
from src.backtest.analysis.calculators.execution_quality_calculator import (
    ExecutionQualityCalculator,
)
from src.backtest.analysis.calculators.portfolio_risk_calculator import (
    PortfolioRiskCalculator,
)
from src.backtest.analysis.calculators.risk_adjusted_calculator import (
    RiskAdjustedCalculator,
)
from src.backtest.analysis.calculators.trading_behavior_calculator import (
    TradingBehaviorCalculator,
)
from src.backtest.domain.metrics import BacktestMetrics, BacktestSummary
from src.backtest.domain.result import BacktestResult, PortfolioSnapshot
from src.backtest.domain.session import BacktestSession


def _timestamp_to_datetime(timestamp: float | int) -> datetime:
    ts = (timestamp / 1000.0) if timestamp > 100000000000 else float(timestamp)
    return datetime.fromtimestamp(ts, tz=timezone.utc)


class BacktestMetricsCalculator:
    """Orchestrates calculation of strategy robustness and performance analytics."""

    def __init__(
            self,
            risk_calculator: Optional[RiskAdjustedCalculator] = None,
            behavior_calculator: Optional[TradingBehaviorCalculator] = None,
            execution_calculator: Optional[ExecutionQualityCalculator] = None,
            portfolio_calculator: Optional[PortfolioRiskCalculator] = None,
    ):
        self._risk_calculator = risk_calculator or RiskAdjustedCalculator()
        self._behavior_calculator = behavior_calculator or TradingBehaviorCalculator()
        self._execution_calculator = execution_calculator or ExecutionQualityCalculator()
        self._portfolio_calculator = portfolio_calculator or PortfolioRiskCalculator()

    def calculate(self, result: BacktestResult) -> BacktestMetrics:
        initial = result.initial_balance
        final = result.final_equity
        absolute_pnl = final - initial
        percentage_return = (
            (final / initial - Decimal("1")) * Decimal("100") if initial else Decimal("0")
        )

        peak = Decimal("0")
        max_drawdown = Decimal("0")
        for snapshot in result.portfolio_snapshots:
            peak = max(peak, snapshot.equity)
            max_drawdown = max(max_drawdown, peak - snapshot.equity)
        max_drawdown_pct = (max_drawdown / peak * Decimal("100")) if peak else Decimal("0")

        fills = result.fills
        orders = result.orders
        buy_count = sum(1 for fill in fills if fill.trade_action == TradeAction.BUY)
        sell_count = sum(1 for fill in fills if fill.trade_action == TradeAction.SELL)
        orders_cancelled = sum(1 for order in orders if order.status == OrderStatus.CANCELLED)

        # 1. Risk-adjusted metrics
        risk_adjusted = self._risk_calculator.calculate(
            snapshots=result.portfolio_snapshots,
            initial_balance=initial,
            final_equity=final,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
        )

        # 2. Trading behavior metrics
        behavior = self._behavior_calculator.calculate(
            fills=fills,
            snapshots=result.portfolio_snapshots,
            initial_balance=initial,
        )

        # 3. Execution quality metrics
        execution = self._execution_calculator.calculate(
            fills=fills,
            orders=orders,
        )

        # 4. Portfolio risk metrics
        portfolio = self._portfolio_calculator.calculate(result)

        total_fees = sum((fill.fee for fill in fills), Decimal("0"))
        total_slippage_cost = sum((fill.slippage_cost for fill in fills), Decimal("0"))
        equity_curve = self._build_equity_curve(result.portfolio_snapshots)

        start_time: Optional[datetime] = None
        end_time: Optional[datetime] = None
        if result.market_series:
            start_time = _timestamp_to_datetime(result.market_series[0].timestamp)
            end_time = _timestamp_to_datetime(result.market_series[-1].timestamp)
        elif result.portfolio_snapshots:
            start_time = _timestamp_to_datetime(result.portfolio_snapshots[0].timestamp)
            end_time = _timestamp_to_datetime(result.portfolio_snapshots[-1].timestamp)

        return BacktestMetrics(
            initial_balance=initial,
            final_equity=final,
            absolute_pnl=absolute_pnl,
            percentage_return=percentage_return,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            orders_submitted=len(orders),
            orders_filled=len(fills),
            orders_cancelled=orders_cancelled,
            buy_count=buy_count,
            sell_count=sell_count,
            round_trips=behavior.round_trips,
            total_fees=total_fees,
            total_slippage_cost=total_slippage_cost,
            risk_adjusted=risk_adjusted,
            behavior=behavior,
            execution=execution,
            portfolio=portfolio,
            total_pnl=absolute_pnl,
            sharpe_ratio=risk_adjusted.sharpe_ratio,
            sortino_ratio=risk_adjusted.sortino_ratio,
            calmar_ratio=risk_adjusted.calmar_ratio,
            annualized_volatility_pct=risk_adjusted.annualized_volatility_pct,
            recovery_factor=risk_adjusted.recovery_factor,
            win_rate_pct=behavior.win_rate_pct,
            profit_factor=behavior.profit_factor,
            expectancy=behavior.expectancy,
            avg_latency_ms=execution.avg_latency_ms,
            avg_slippage_bps=execution.avg_slippage_bps,
            total_trades=behavior.round_trips,
            total_orders=len(orders),
            total_fills=len(fills),
            equity_curve=equity_curve,
            data_points=len(result.market_series) if isinstance(result.market_series, (list, tuple)) else 0,
            start_time=start_time,
            end_time=end_time,
        )

    def summarize(self, session: BacktestSession, metrics: BacktestMetrics) -> BacktestSummary:
        return BacktestSummary(
            session_id=session.id,
            ticker_symbol=session.ticker_symbol,
            status=session.status.value,
            return_pct=metrics.percentage_return,
            absolute_pnl=metrics.absolute_pnl,
            max_drawdown_pct=metrics.max_drawdown_pct,
            round_trips=metrics.round_trips,
            orders_filled=metrics.orders_filled,
            orders_cancelled=metrics.orders_cancelled,
            sharpe_ratio=metrics.sharpe_ratio,
            sortino_ratio=metrics.sortino_ratio,
            profit_factor=metrics.profit_factor,
            win_rate_pct=metrics.win_rate_pct,
            data_points=metrics.data_points,
            start_time=metrics.start_time,
            end_time=metrics.end_time,
        )

    @staticmethod
    def _build_equity_curve(snapshots: list[PortfolioSnapshot]) -> list[dict[str, Any]]:
        if not snapshots:
            return []

        max_curve_points = 500
        if len(snapshots) <= max_curve_points:
            selected_snapshots = snapshots
        else:
            step = len(snapshots) / max_curve_points
            selected_indices = {int(i * step) for i in range(max_curve_points)}
            selected_indices.add(0)
            selected_indices.add(len(snapshots) - 1)
            selected_snapshots = [snapshots[i] for i in sorted(selected_indices) if i < len(snapshots)]

        curve = []
        for s in selected_snapshots:
            ts = int(s.timestamp * 1000) if s.timestamp < 100000000000 else int(s.timestamp)
            curve.append({
                "timestamp": ts,
                "equity": float(s.equity),
                "balance": float(s.cash),
            })
        return curve
