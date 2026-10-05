from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.decision.decision_manager import DecisionManager
from src.trading.decision.trading_decision import TradingDecision


class DecisionInspectorInput(BaseModel):
    decision_id: Optional[str] = Field(
        default=None,
        description="ID of the specific trading decision to inspect.",
    )
    order_id: Optional[str] = Field(
        default=None,
        description="ID/UUID of an order to find its originating trading decision.",
    )
    ticker_symbol: Optional[str] = Field(
        default=None,
        description="Filter recent decisions by ticker symbol (e.g. 'BTC_USD').",
    )
    limit: int = Field(
        default=5,
        description="Maximum number of recent decisions to return when searching by symbol.",
    )


class DecisionInspectorTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "inspect_trading_decision"
    description: str = (
        "Inspects first-class trading decisions to explain exactly WHY an order was executed, "
        "rejected, or sized a certain way. Returns market snapshot, regime metrics, strategy votes, "
        "dynamic sizing formulas, portfolio risk limits, and configuration commit hashes."
    )
    args_schema: Type[BaseModel] = DecisionInspectorInput
    decision_manager: DecisionManager

    def __init__(self, decision_manager: DecisionManager):
        super().__init__(decision_manager=decision_manager)

    def _run(
            self,
            decision_id: Optional[str] = None,
            order_id: Optional[str] = None,
            ticker_symbol: Optional[str] = None,
            limit: int = 5,
    ) -> str:
        if decision_id:
            decision = self.decision_manager.get_decision(decision_id.strip())
            if not decision:
                # Also fallback to order lookup
                decision = self.decision_manager.get_decision_by_order_id(decision_id.strip())
            if not decision:
                return f"No trading decision found for ID '{decision_id}'."
            return self._format_decision_detail(decision)

        if order_id:
            decision = self.decision_manager.get_decision_by_order_id(order_id.strip())
            if not decision:
                return f"No trading decision found associated with order ID '{order_id}'."
            return self._format_decision_detail(decision)

        decisions = self.decision_manager.list_decisions(
            ticker_symbol=ticker_symbol.strip() if ticker_symbol else None,
            limit=limit,
        )
        if not decisions:
            filter_msg = f" for '{ticker_symbol}'" if ticker_symbol else ""
            return f"No recent trading decisions found{filter_msg}."

        return self._format_decision_list(decisions)

    @classmethod
    def _format_decision_detail(cls, d: TradingDecision) -> str:
        dt = datetime.fromtimestamp(d.timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            f"=== Trading Decision {d.decision_id} ===",
            f"Timestamp: {dt}",
            f"Asset / Exchange: {d.ticker_symbol} on {d.exchange}",
            f"Action: {d.trade_action.value}",
            f"Status: {d.status.value}",
        ]
        if d.resulting_order_id:
            lines.append(f"Resulting Order ID: {d.resulting_order_id}")
        if d.rejection_reason:
            lines.append(f"Rejection Reason: {d.rejection_reason}")
        if d.commit_hash:
            lines.append(f"Configuration Commit: {d.commit_hash}")

        # Market Snapshot
        lines.append("\n[Market Snapshot]")
        lines.append(f"  Close Price: ${d.market_snapshot.close_price}")
        if d.market_snapshot.bid_price is not None and d.market_snapshot.ask_price is not None:
            lines.append(f"  Bid: ${d.market_snapshot.bid_price} | Ask: ${d.market_snapshot.ask_price}")
        if d.market_snapshot.spread_pct is not None:
            lines.append(f"  Spread: {float(d.market_snapshot.spread_pct) * 100:.3f}%")
        lines.append(f"  Candles Count: {d.market_snapshot.candles_count}")

        # Regime Snapshot
        lines.append("\n[Market Regime]")
        lines.append(f"  Regime: {d.regime_snapshot.regime}")
        lines.append(f"  Volatility (ATR%): {d.regime_snapshot.volatility * 100:.2f}%")
        lines.append(f"  Trend Strength: {d.regime_snapshot.trend_strength:+.3f}")
        lines.append(f"  Exposure Multiplier: {d.regime_snapshot.exposure_multiplier:.2f}x")

        # Consensus Snapshot
        lines.append("\n[Strategy Consensus]")
        lines.append(f"  Quorum Reached: {d.consensus_snapshot.quorum} (Vote Ratio: {d.consensus_snapshot.vote_ratio * 100:.1f}%)")
        lines.append(f"  Consensus Factor: {d.consensus_snapshot.factor}")
        if d.consensus_snapshot.winning_strategy:
            lines.append(f"  Winning Strategy: {d.consensus_snapshot.winning_strategy}")
        lines.append("  Votes:")
        for strat, vote in sorted(d.consensus_snapshot.votes.items()):
            weight = d.consensus_snapshot.weights.get(strat, 1.0)
            lines.append(f"    - {strat}: {'BUY' if vote else 'HOLD/REJECT'} (Weight: {weight})")

        # Dynamic Sizing
        lines.append("\n[Position Sizing]")
        if d.sizing_snapshot.formula:
            lines.append(f"  Formula: {d.sizing_snapshot.formula}")
        if d.sizing_snapshot.calculated_quantity is not None:
            lines.append(f"  Calculated Quantity: {d.sizing_snapshot.calculated_quantity}")
        lines.append(f"  Min Asset Quantity: {d.sizing_snapshot.min_quantity}")
        if d.sizing_snapshot.final_quantity is not None:
            lines.append(f"  Final Order Quantity: {d.sizing_snapshot.final_quantity}")

        # Portfolio Snapshot & Risk Guard
        lines.append("\n[Portfolio & Risk Guard]")
        lines.append(f"  Total Equity: ${d.portfolio_snapshot.total_equity:.2f}")
        lines.append(f"  Available Cash: ${d.portfolio_snapshot.available_cash:.2f}")
        lines.append(f"  Total Exposure: {d.portfolio_snapshot.current_exposure_pct * 100:.1f}%")
        lines.append(f"  Asset Concentration: {d.portfolio_snapshot.asset_exposure_pct * 100:.1f}%")
        lines.append(f"  Current Drawdown: {d.portfolio_snapshot.drawdown_pct * 100:.2f}%")
        lines.append(f"  Risk Guard Passed: {d.risk_evaluation.passed}")
        if d.risk_evaluation.rejection_reason:
            lines.append(f"  Guard Violation: {d.risk_evaluation.rejection_reason}")

        # Health Evaluation
        if d.health_evaluation:
            lines.append("\n[Trading Health]")
            lines.append(f"  State: {d.health_evaluation.state} (Allowed: {d.health_evaluation.allowed})")
            if d.health_evaluation.active_conditions:
                lines.append(f"  Active Conditions: {', '.join(d.health_evaluation.active_conditions)}")

        return "\n".join(lines)

    @classmethod
    def _format_decision_list(cls, decisions: list[TradingDecision]) -> str:
        lines = [f"Found {len(decisions)} Recent Trading Decision(s):"]
        for d in decisions:
            dt = datetime.fromtimestamp(d.timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            order_info = f" -> Order: {d.resulting_order_id}" if d.resulting_order_id else ""
            reason_info = f" (Reason: {d.rejection_reason})" if d.rejection_reason else ""
            lines.append(
                f"- [{dt}] ID: {d.decision_id} | {d.ticker_symbol} {d.trade_action.value} | Status: {d.status.value}{order_info}{reason_info}"
            )
        lines.append("\nUse 'inspect_trading_decision' with a specific decision_id or order_id for full details.")
        return "\n".join(lines)
