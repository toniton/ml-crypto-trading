from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from api.interfaces.trade import Trade
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.server.services.asset_performance_service import AssetPerformanceService
from src.trading.analytics.strategy_optimizer import StrategyOptimizer
from src.trading.session.session_manager import SessionManager


class StrategyOptimizerInput(BaseModel):
    action: str = Field(
        default="calibrate",
        description="Optimization action: 'calibrate', 'windows', 'redundancy', or 'proposal'.",
    )
    ticker_symbol: Optional[str] = Field(
        default=None,
        description="Ticker symbol (e.g. 'BTC_USD') to optimize.",
    )
    lookback_days: int = Field(
        default=30,
        description="Number of days of trade history to analyze (default: 30).",
    )
    timezone: str = Field(
        default="UTC",
        description="Target timezone for schedule optimization (default: 'UTC').",
    )


class StrategyOptimizerTool(BaseTool, ApplicationLoggingMixin):
    name: str = "strategy_optimizer"
    description: str = (
        "Empirically optimizes strategy weights, discovers profitable trading windows, "
        "detects redundant co-voting strategies, and generates configuration proposals."
    )
    args_schema: Type[BaseModel] = StrategyOptimizerInput

    database_manager: Optional[DatabaseManager] = None
    session_manager: Optional[SessionManager] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(
            self,
            database_manager: Optional[DatabaseManager] = None,
            session_manager: Optional[SessionManager] = None,
    ):
        super().__init__(database_manager=database_manager, session_manager=session_manager)

    def _run(  # pylint: disable=arguments-differ,redefined-outer-name
            self,
            action: str = "calibrate",
            ticker_symbol: Optional[str] = None,
            lookback_days: int = 30,
            timezone: str = "UTC",
    ) -> str:
        self.app_logger.info(
            f"Strategy optimizer tool called (action={action}, symbol={ticker_symbol}, lookback={lookback_days}d)"
        )
        trades = self._gather_trades(ticker_symbol=ticker_symbol, lookback_days=lookback_days)
        if not trades:
            return "No historical trades found for the specified asset/period to perform optimization."

        norm_action = action.strip().lower()
        if norm_action == "windows":
            return self._run_windows(trades, ticker_symbol, timezone)
        if norm_action == "redundancy":
            return self._run_redundancy(trades)
        if norm_action == "proposal":
            return self._run_proposal(trades, ticker_symbol, timezone)

        return self._run_calibrate(trades)

    @staticmethod
    def _run_windows(trades: list[Trade], ticker_symbol: Optional[str], target_tz: str) -> str:
        windows = StrategyOptimizer.optimize_trading_windows(trades, timezone_str=target_tz)
        if not windows:
            return f"No distinct profitable hourly windows discovered for {ticker_symbol or 'all assets'}."
        lines = [f"### 🕒 Recommended Trading Windows ({target_tz})\n"]
        for i, w in enumerate(windows, 1):
            days_str = ", ".join(d.name.title() for d in w.days)
            lines.append(
                f"**Window #{i}**: {days_str} from {w.start_time.strftime('%H:%M')} to {w.end_time.strftime('%H:%M')}"
            )
        return "\n".join(lines)

    @staticmethod
    def _run_redundancy(trades: list[Trade]) -> str:
        redundancies = StrategyOptimizer.detect_strategy_redundancies(trades)
        if not redundancies:
            return "No high-redundancy strategy pairs detected (all co-voting agreement rates < 85%)."
        lines = ["### ⚠️ Strategy Redundancy Analysis\n"]
        for r in redundancies:
            lines.append(
                f"- **{r.strategy_a} & {r.strategy_b}**: {r.agreement_rate_pct}% agreement "
                f"across {r.co_sponsored_trades} trade(s). {r.recommendation}"
            )
        return "\n".join(lines)

    @staticmethod
    def _run_proposal(trades: list[Trade], ticker_symbol: Optional[str], target_tz: str) -> str:
        sym = ticker_symbol or "PORTFOLIO"
        active_strats: set[str] = set()
        for t in trades:
            if t.entry_strategy_attributions:
                active_strats.update(t.entry_strategy_attributions.keys())
            elif t.winning_strategy:
                active_strats.add(t.winning_strategy)
        current_config = {
            "strategies": [{"name": s, "weight": 1.0} for s in sorted(active_strats)]
        }
        prop = StrategyOptimizer.generate_optimization_proposal(sym, current_config, trades, timezone_str=target_tz)
        return (
                f"### 📋 Optimization Proposal Generated\n\n"
                f"**Summary**: {prop.summary}\n\n"
                f"**Expected Effect**: {prop.expected_effect}\n\n"
                f"**Proposed Changes ({len(prop.changes)})**:\n"
                + "\n".join(f"- `{c.path}`: `{c.old_value}` -> `{c.new_value}` ({c.reason})" for c in prop.changes)
        )

    @staticmethod
    def _run_calibrate(trades: list[Trade]) -> str:
        active_weights: dict[str, float] = {}
        for t in trades:
            if t.entry_strategy_attributions:
                for s in t.entry_strategy_attributions:
                    active_weights[s] = 1.0
            elif t.winning_strategy:
                active_weights[t.winning_strategy] = 1.0

        recommendations = StrategyOptimizer.calibrate_strategy_weights(trades, active_weights)
        lines = ["### ⚖️ Strategy Weight Calibration Recommendations\n"]
        for rec in recommendations:
            lines.append(
                f"- **{rec.strategy_name}**: Current={rec.current_weight:.2f} -> "
                f"**Recommended={rec.recommended_weight:.2f}** "
                f"(Win Rate: {rec.win_rate_pct:.1f}%, PF: {rec.profit_factor:.2f}, Trades: {rec.total_trades})\n"
                f"  _{rec.rationale}_"
            )
        return "\n".join(lines)

    def _gather_trades(self, ticker_symbol: Optional[str], lookback_days: int) -> list[Trade]:
        trades: list[Trade] = []
        if self.database_manager is not None:
            trades.extend(self._fetch_db_trades(ticker_symbol, lookback_days))
        return trades

    def _fetch_db_trades(self, ticker_symbol: Optional[str], lookback_days: int) -> list[Trade]:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=max(1, lookback_days))
        with self.database_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresOrderRepository)
            if ticker_symbol:
                orders = repo.get_completed_by_ticker_and_executed_range(
                    ticker_symbol=ticker_symbol.strip(),
                    start=start,
                    end=now,
                )
                symbols = [ticker_symbol.strip()]
            else:
                orders = repo.get_completed_by_executed_range(start=start, end=now)
                symbols = list({o.ticker_symbol for o in orders})

            all_trades: list[Trade] = []
            for symbol in symbols:
                sym_orders = [o for o in orders if o.ticker_symbol == symbol]
                all_trades.extend(AssetPerformanceService.extract_trades(symbol, sym_orders))
            return all_trades
