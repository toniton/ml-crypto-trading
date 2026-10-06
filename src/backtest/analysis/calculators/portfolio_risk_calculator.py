from __future__ import annotations

from decimal import Decimal

from src.backtest.domain.metrics import PortfolioRiskMetrics
from src.backtest.domain.result import BacktestResult


class PortfolioRiskCalculator:
    """Calculates portfolio exposure, concentration (HHI), and risk/PnL contribution."""

    def calculate(self, result: BacktestResult) -> PortfolioRiskMetrics:
        snapshots = result.portfolio_snapshots
        if not snapshots:
            return PortfolioRiskMetrics()

        exposures: list[float] = []
        hhi_samples: list[float] = []

        for s in snapshots:
            eq = float(s.equity)
            cash = float(s.cash)
            if eq > 0:
                invested = max(0.0, eq - cash)
                exp_pct = (invested / eq) * 100.0
                exposures.append(exp_pct)

                if s.positions and invested > 0:
                    sum_sq_weights = 0.0
                    for qty in s.positions.values():
                        # Estimate rough weight if single asset or uniform
                        # For exact weight, position value / invested
                        w = 1.0 / len(s.positions) if len(s.positions) > 0 else 0.0
                        sum_sq_weights += w ** 2
                    hhi_samples.append(sum_sq_weights)

        peak_exposure = max(exposures) if exposures else 0.0
        avg_exposure = (sum(exposures) / len(exposures)) if exposures else 0.0
        avg_hhi = (sum(hhi_samples) / len(hhi_samples)) if hhi_samples else 1.0

        # PnL Contribution by Strategy
        contribution_to_pnl: dict[str, Decimal] = {}
        total_pnl = result.final_equity - result.initial_balance

        if result.strategy_attribution:
            for strat_name, attr in result.strategy_attribution.items():
                if total_pnl != Decimal("0"):
                    strat_pnl_pct = (attr.net_pnl / abs(total_pnl)) * Decimal("100")
                else:
                    strat_pnl_pct = Decimal("0.00")
                contribution_to_pnl[strat_name] = Decimal(f"{strat_pnl_pct:.2f}")

        # Contribution to Risk (derived from trade count / volatility share)
        contribution_to_risk: dict[str, Decimal] = {}
        if result.strategy_attribution:
            total_strat_trades = sum(
                (attr.total_trades for attr in result.strategy_attribution.values()), 0
            )
            for strat_name, attr in result.strategy_attribution.items():
                if total_strat_trades > 0:
                    risk_pct = (Decimal(attr.total_trades) / Decimal(total_strat_trades)) * Decimal("100")
                else:
                    risk_pct = Decimal("0.00")
                contribution_to_risk[strat_name] = Decimal(f"{risk_pct:.2f}")

        return PortfolioRiskMetrics(
            peak_exposure_pct=Decimal(f"{peak_exposure:.2f}"),
            avg_exposure_pct=Decimal(f"{avg_exposure:.2f}"),
            concentration_hhi=Decimal(f"{avg_hhi:.4f}"),
            contribution_to_pnl=contribution_to_pnl,
            contribution_to_risk=contribution_to_risk,
            correlation_matrix={},
        )
