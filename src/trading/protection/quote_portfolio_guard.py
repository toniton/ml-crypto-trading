from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from src.trading.protection.portfolio_policy_resolver import EffectivePortfolioConfig
from src.trading.regimes.market_regime import MarketRegime


@dataclass(frozen=True)
class PortfolioRiskMetrics:
    total_equity: Decimal
    total_cash: Decimal
    reserved_cash: Decimal
    available_cash: Decimal
    invested_notional: Decimal
    total_exposure_pct: Decimal
    asset_notional: Decimal
    asset_concentration_pct: Decimal
    peak_equity: Decimal
    drawdown_pct: Decimal
    daily_loss_pct: Decimal
    open_position_count: int


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    reason: Optional[str] = None
    violations: tuple[str, ...] = ()


class QuotePortfolioGuard:
    """Evaluates proposed orders against portfolio risk metrics, market regime, and guard policy."""

    @staticmethod
    def evaluate(
            asset_symbol: str,
            order_cost: Decimal,
            risk: PortfolioRiskMetrics,
            regime: MarketRegime,
            config: EffectivePortfolioConfig,
    ) -> GuardDecision:
        if not config.guard.enabled:
            return GuardDecision(allowed=True)

        violations: list[str] = []
        cost_dec = Decimal(str(order_cost))

        # 1. Unreserved Available Cash Check
        if cost_dec > risk.available_cash:
            violations.append(
                f"Insufficient unreserved cash: required {cost_dec}, available {risk.available_cash}"
            )

        # 2. Minimum Quote Reserve Check
        required_reserve = risk.total_equity * config.guard.min_quote_reserve
        remaining_unreserved = risk.available_cash - cost_dec
        if remaining_unreserved < required_reserve:
            violations.append(
                f"Quote reserve breached: remaining unreserved cash {remaining_unreserved} "
                f"< required reserve {required_reserve}"
            )

        # 3. Maximum Quote Exposure Check
        projected_invested = risk.invested_notional + cost_dec
        if risk.total_equity > Decimal("0"):
            projected_exposure = projected_invested / risk.total_equity
            if projected_exposure > config.guard.max_quote_exposure:
                violations.append(
                    f"Max quote exposure exceeded: projected {projected_exposure:.2%} "
                    f"> limit {config.guard.max_quote_exposure:.2%}"
                )

        # 4. Maximum Per-Asset Concentration Check
        effective_max_asset = (
            config.effective_max_per_asset
            if config.regime.enabled
            else config.exposure.max_per_asset
        )
        projected_asset_notional = risk.asset_notional + cost_dec
        if risk.total_equity > Decimal("0") and effective_max_asset is not None:
            projected_concentration = projected_asset_notional / risk.total_equity
            if projected_concentration > effective_max_asset:
                violations.append(
                    f"Asset concentration limit exceeded for {asset_symbol}: "
                    f"projected {projected_concentration:.2%} > limit {effective_max_asset:.2%}"
                )

        # 5. Maximum Total Portfolio Exposure Check
        effective_max_total = (
            config.effective_max_total
            if config.regime.enabled
            else config.exposure.max_total
        )
        if risk.total_equity > Decimal("0") and effective_max_total is not None:
            projected_total_exposure = projected_invested / risk.total_equity
            if projected_total_exposure > effective_max_total:
                violations.append(
                    f"Max total portfolio exposure exceeded: projected {projected_total_exposure:.2%} "
                    f"> limit {effective_max_total:.2%}"
                )

        # 6. Maximum Drawdown Check
        if config.guard.max_drawdown is not None:
            max_allowed_dd = -abs(config.guard.max_drawdown)
            if risk.drawdown_pct < max_allowed_dd:
                violations.append(
                    f"Portfolio drawdown limit exceeded: current {risk.drawdown_pct:.2%} "
                    f"< limit {max_allowed_dd:.2%}"
                )

        # 7. Maximum Position Count Check
        if config.guard.max_position_count is not None:
            is_new_position = risk.asset_notional <= Decimal("0")
            projected_count = risk.open_position_count + (1 if is_new_position else 0)
            if projected_count > config.guard.max_position_count:
                violations.append(
                    f"Max position count exceeded: projected {projected_count} "
                    f"> limit {config.guard.max_position_count}"
                )

        # 8. Market Regime Gating
        if config.regime.enabled:
            if regime == MarketRegime.ILLIQUID:
                violations.append("Market regime is ILLIQUID: new orders prohibited")

        if violations:
            return GuardDecision(
                allowed=False,
                reason="; ".join(violations),
                violations=tuple(violations),
            )

        return GuardDecision(allowed=True)
