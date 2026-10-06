from __future__ import annotations

import math
from decimal import Decimal
from typing import Optional

from src.backtest.domain.metrics import RiskAdjustedMetrics
from src.backtest.domain.result import PortfolioSnapshot


class RiskAdjustedCalculator:
    """Calculates risk-adjusted return and drawdown metrics from portfolio snapshots."""

    SECONDS_PER_YEAR = 365.25 * 24 * 3600

    def calculate(
            self,
            snapshots: list[PortfolioSnapshot],
            initial_balance: Decimal,
            final_equity: Decimal,
            max_drawdown: Decimal,
            max_drawdown_pct: Decimal,
    ) -> RiskAdjustedMetrics:
        if len(snapshots) < 2:
            recovery_factor = (
                (final_equity - initial_balance) / max_drawdown
                if max_drawdown > Decimal("0")
                else None
            )
            return RiskAdjustedMetrics(
                max_drawdown=max_drawdown,
                max_drawdown_pct=max_drawdown_pct,
                recovery_factor=Decimal(f"{recovery_factor:.2f}") if recovery_factor is not None else None,
            )

        returns: list[float] = []
        for i in range(1, len(snapshots)):
            prev_eq = float(snapshots[i - 1].equity)
            curr_eq = float(snapshots[i].equity)
            if prev_eq > 0:
                returns.append((curr_eq - prev_eq) / prev_eq)

        if not returns:
            return RiskAdjustedMetrics(
                max_drawdown=max_drawdown,
                max_drawdown_pct=max_drawdown_pct,
            )

        mean_return = math.fsum(returns) / len(returns)
        variance = (
            sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
            if len(returns) > 1
            else 0.0
        )
        std_dev = math.sqrt(variance)

        annual_factor, years = self._compute_annual_factor(snapshots)

        # 1. Volatility
        annualized_vol_pct = (
            Decimal(f"{std_dev * annual_factor * 100:.2f}")
            if std_dev > 0
            else Decimal("0.00")
        )

        # 2. Sharpe Ratio
        sharpe_ratio: Optional[Decimal] = None
        if std_dev > 0:
            sharpe = (mean_return / std_dev) * annual_factor
            sharpe_ratio = Decimal(f"{sharpe:.4f}")

        # 3. Downside Deviation & Sortino Ratio
        downside_sq_sum = sum(r ** 2 for r in returns if r < 0)
        downside_dev = math.sqrt(downside_sq_sum / len(returns)) if len(returns) > 0 else 0.0
        downside_dev_pct: Optional[Decimal] = (
            Decimal(f"{downside_dev * annual_factor * 100:.2f}")
            if downside_dev > 0
            else None
        )

        sortino_ratio: Optional[Decimal] = None
        if downside_dev > 0:
            sortino = (mean_return / downside_dev) * annual_factor
            sortino_ratio = Decimal(f"{sortino:.4f}")
        elif mean_return > 0 and std_dev > 0:
            sortino_ratio = Decimal("99.99")

        # 4. Calmar Ratio
        calmar_ratio: Optional[Decimal] = None
        if max_drawdown_pct > Decimal("0") and initial_balance > Decimal("0"):
            total_return_ratio = float(final_equity / initial_balance)
            if years > 0 and total_return_ratio > 0:
                annualized_return_pct = ((total_return_ratio ** (1.0 / years)) - 1.0) * 100.0
            else:
                annualized_return_pct = float(
                    ((final_equity - initial_balance) / initial_balance) * Decimal("100")
                )
            calmar = Decimal(f"{annualized_return_pct / float(max_drawdown_pct):.4f}")
            calmar_ratio = calmar

        # 5. Recovery Factor
        recovery_factor: Optional[Decimal] = None
        if max_drawdown > Decimal("0"):
            abs_pnl = final_equity - initial_balance
            recovery_factor = Decimal(f"{abs_pnl / max_drawdown:.2f}")

        return RiskAdjustedMetrics(
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            annualized_volatility_pct=annualized_vol_pct,
            downside_deviation_pct=downside_dev_pct,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            recovery_factor=recovery_factor,
        )

    def _compute_annual_factor(self, snapshots: list[PortfolioSnapshot]) -> tuple[float, float]:
        if len(snapshots) < 2:
            return math.sqrt(252), 1.0

        ts_first = snapshots[0].timestamp
        ts_last = snapshots[-1].timestamp
        total_time_span = float(ts_last - ts_first)
        if total_time_span > 100000000:
            total_time_span /= 1000.0

        avg_step = total_time_span / (len(snapshots) - 1) if len(snapshots) > 1 else 0.0

        if avg_step > 0:
            periods_per_year = self.SECONDS_PER_YEAR / avg_step
            annual_factor = math.sqrt(periods_per_year)
            years = total_time_span / self.SECONDS_PER_YEAR
        else:
            annual_factor = math.sqrt(252)
            years = 1.0

        return annual_factor, max(years, 0.0001)
