from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from api.interfaces.trade import Trade
from src.agent.configuration.configuration_service import ConfigurationService
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.server.services.asset_performance_service import AssetPerformanceService
from src.trading.analytics.strategy_optimizer import StrategyOptimizer


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

    database_manager: DatabaseManager
    configuration_service: ConfigurationService

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(
            self,
            database_manager: DatabaseManager,
            configuration_service: ConfigurationService,
    ):
        super().__init__(
            database_manager=database_manager,
            configuration_service=configuration_service,
        )

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
        norm_action = action.strip().lower()

        asset_config: Optional[dict[str, Any]] = None
        base_commit_hash: Optional[str] = None
        if norm_action in ("calibrate", "proposal"):
            asset_config, base_commit_hash, err = self._get_asset_config_snapshot(ticker_symbol)
            if err is not None or asset_config is None:
                return err or "Error loading asset configuration."

        trades = self._gather_trades(ticker_symbol=ticker_symbol, lookback_days=lookback_days)
        if not trades:
            return "No historical trades found for the specified asset/period to perform optimization."

        if norm_action == "windows":
            return self._run_windows(trades, ticker_symbol, timezone)
        if norm_action == "redundancy":
            return self._run_redundancy(trades)
        if norm_action == "proposal":
            return self._run_proposal(
                trades,
                ticker_symbol,
                timezone,
                asset_config,
                base_commit_hash=base_commit_hash,
            )

        return self._run_calibrate(trades, ticker_symbol, asset_config)

    def _get_asset_config_snapshot(
            self, ticker_symbol: Optional[str]
    ) -> tuple[Optional[dict[str, Any]], Optional[str], Optional[str]]:
        if not ticker_symbol:
            return None, None, "Error: 'ticker_symbol' is required for strategy calibration and proposal generation."

        snapshot_res = self.configuration_service.get_asset_config_snapshot(ticker_symbol)
        if isinstance(snapshot_res, tuple) and len(snapshot_res) == 2:
            asset_config, commit_hash = snapshot_res
        else:
            asset_config = self.configuration_service.get_asset_config(ticker_symbol)
            commit_hash = None

        if asset_config is None:
            return None, None, f"Error: Asset '{ticker_symbol}' is not configured in the active configuration."

        return asset_config, commit_hash, None

    def _get_asset_config(self, ticker_symbol: Optional[str]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        cfg, _, err = self._get_asset_config_snapshot(ticker_symbol)
        return cfg, err

    def _get_base_commit_hash(self) -> Optional[str]:
        return self.configuration_service.get_head_commit_hash()

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

    def _run_proposal(
            self,
            trades: list[Trade],
            ticker_symbol: Optional[str],
            target_tz: str,
            asset_config: dict[str, Any],
            base_commit_hash: Optional[str] = None,
    ) -> str:
        sym = ticker_symbol.strip() if ticker_symbol else "PORTFOLIO"
        prop = StrategyOptimizer.generate_optimization_proposal(
            sym,
            asset_config,
            trades,
            timezone_str=target_tz,
            base_commit_hash=base_commit_hash,
        )
        base_commit_str = f"**Base Commit**: `{prop.base_commit_hash}`\n\n" if prop.base_commit_hash else ""
        changes = list(prop.changes)
        changes_str = (
            "\n".join(f"- `{c.path}`: `{c.old_value}` -> `{c.new_value}` ({c.reason})" for c in changes)
            if changes else "_No changes proposed (current weights and schedules are already optimal)._"
        )
        return (
            f"### 📋 Optimization Proposal Generated for {sym}\n\n"
            f"**Summary**: {prop.summary}\n\n"
            f"{base_commit_str}"
            f"**Expected Effect**: {prop.expected_effect}\n\n"
            f"**Proposed Changes ({len(prop.changes)})**:\n"
            f"{changes_str}"
        )

    @staticmethod
    def _run_calibrate(
            trades: list[Trade],
            ticker_symbol: Optional[str],
            asset_config: dict[str, Any],
    ) -> str:
        strategies = asset_config.get("strategies", [])
        if not strategies:
            return f"Error: No strategies configured for asset '{ticker_symbol}'."

        active_weights: dict[str, float] = {
            strat.get("name"): float(strat.get("weight", 1.0))
            for strat in strategies
            if strat.get("name") and strat.get("enabled", True)
        }
        if not active_weights:
            return f"Error: No active/enabled strategies configured for asset '{ticker_symbol}'."

        recommendations = StrategyOptimizer.calibrate_strategy_weights(trades, active_weights)
        lines = [
            f"### ⚖️ Strategy Weight Calibration Recommendations for {ticker_symbol}\n"
            f"*(Empirical heuristic based on historical trade attribution; validation required before live use)*\n"
        ]
        for rec in recommendations:
            lines.append(
                f"- **{rec.strategy_name}**: Current={rec.current_weight:.2f} -> "
                f"**Recommended={rec.recommended_weight:.2f}** "
                f"(Win Rate: {rec.win_rate_pct:.1f}%, PF: {rec.profit_factor:.2f}, Trades: {rec.total_trades})\n"
                f"  _{rec.rationale}_"
            )
        return "\n".join(lines)

    def _gather_trades(self, ticker_symbol: Optional[str], lookback_days: int) -> list[Trade]:
        return self._fetch_db_trades(ticker_symbol, lookback_days)

    def _fetch_db_trades(self, ticker_symbol: Optional[str], lookback_days: int) -> list[Trade]:
        now = datetime.now(timezone.utc)
        target_start = now - timedelta(days=max(1, lookback_days))
        fetch_start = now - timedelta(days=int(max(1, lookback_days) * 1.5) + 1)
        with self.database_manager.get_unit_of_work() as uow:
            repo = uow.get_repository(PostgresOrderRepository)
            if ticker_symbol:
                orders = repo.get_completed_by_ticker_and_executed_range(
                    ticker_symbol=ticker_symbol.strip(),
                    start=fetch_start,
                    end=now,
                )
                symbols = [ticker_symbol.strip()]
            else:
                orders = repo.get_completed_by_executed_range(start=fetch_start, end=now)
                symbols = list({o.ticker_symbol for o in orders})

            all_trades: list[Trade] = []
            for symbol in symbols:
                sym_orders = [o for o in orders if o.ticker_symbol == symbol]
                trades = AssetPerformanceService.extract_trades(symbol, sym_orders)
                valid_trades = [t for t in trades if t.exit_timestamp >= target_start.timestamp()]
                all_trades.extend(valid_trades)
            return all_trades
