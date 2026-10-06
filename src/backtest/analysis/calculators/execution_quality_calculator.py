from __future__ import annotations

from decimal import Decimal

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus
from src.backtest.domain.metrics import ExecutionQualityMetrics
from src.backtest.domain.result import BacktestFill


class ExecutionQualityCalculator:
    """Calculates execution metrics including slippage, spreads, latency, and fill ratios."""

    def calculate(
            self,
            fills: list[BacktestFill],
            orders: list[Order],
    ) -> ExecutionQualityMetrics:
        orders_submitted = len(orders)
        orders_filled = len(fills)
        orders_cancelled = sum(1 for order in orders if order.status == OrderStatus.CANCELLED)

        fill_ratio_pct = (
            Decimal(f"{(orders_filled / orders_submitted) * 100:.2f}")
            if orders_submitted > 0
            else Decimal("0.00")
        )
        rejection_ratio_pct = (
            Decimal(f"{(orders_cancelled / orders_submitted) * 100:.2f}")
            if orders_submitted > 0
            else Decimal("0.00")
        )

        if not fills:
            return ExecutionQualityMetrics(
                fill_ratio_pct=fill_ratio_pct,
                rejection_ratio_pct=rejection_ratio_pct,
            )

        total_expected_price = Decimal("0")
        total_fill_price = Decimal("0")
        total_slippage_bps = Decimal("0")
        total_slippage_per_unit = Decimal("0")
        total_slippage_cost = Decimal("0")
        total_spread_bps = Decimal("0")
        total_latency_ms = 0.0

        for fill in fills:
            total_expected_price += fill.requested_price
            total_fill_price += fill.execution_price
            total_slippage_cost += fill.slippage_cost
            total_slippage_per_unit += fill.slippage_per_unit

            if fill.requested_price > Decimal("0"):
                diff = abs(fill.execution_price - fill.requested_price)
                bps = (diff / fill.requested_price) * Decimal("10000")
                total_slippage_bps += bps

            if fill.market_price > Decimal("0"):
                spread_diff = abs(fill.execution_price - fill.market_price)
                spread_bps = (spread_diff / fill.market_price) * Decimal("10000")
                total_spread_bps += spread_bps

            latency_s = float(fill.executed_at - fill.submitted_at)
            if latency_s > 100000000:
                latency_s /= 1000.0
            total_latency_ms += max(0.0, latency_s * 1000.0)

        count = len(fills)
        avg_expected_price = Decimal(f"{total_expected_price / count:.4f}")
        avg_fill_price = Decimal(f"{total_fill_price / count:.4f}")
        avg_slippage_bps = Decimal(f"{total_slippage_bps / count:.2f}")
        avg_slippage_per_unit = Decimal(f"{total_slippage_per_unit / count:.4f}")
        avg_spread_bps = Decimal(f"{total_spread_bps / count:.2f}")
        avg_latency = total_latency_ms / count

        return ExecutionQualityMetrics(
            avg_expected_price=avg_expected_price,
            avg_fill_price=avg_fill_price,
            avg_slippage_bps=avg_slippage_bps,
            avg_slippage_per_unit=avg_slippage_per_unit,
            total_slippage_cost=total_slippage_cost,
            avg_spread_bps=avg_spread_bps,
            avg_latency_ms=avg_latency,
            fill_ratio_pct=fill_ratio_pct,
            rejection_ratio_pct=rejection_ratio_pct,
        )
