from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from api.interfaces.trade import Trade
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.server.services.asset_performance_service import AssetPerformanceService
from src.trading.analytics.trade_attribution_service import (
    AttributionMetrics,
    TradeAttributionService,
)
from src.trading.session.session_manager import SessionManager


class TradeAttributionInput(BaseModel):
    dimension: str = Field(
        default="strategy",
        description="Attribution dimension: 'strategy' (default), 'commit', 'symbol', or 'overall'.",
    )
    ticker_symbol: Optional[str] = Field(
        default=None,
        description="Optional ticker symbol (e.g. 'BTC_USD') to filter trades.",
    )
    lookback_days: int = Field(
        default=30,
        description="Number of days to look back for historical trades (default: 30).",
    )


class TradeAttributionTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_trade_attribution"
    description: str = (
        "Calculates multidimensional P&L attribution and execution statistics "
        "(win rate, profit factor, gross/net PnL, fees, slippage, trade duration) "
        "across strategies, commits, or symbols for historical or live trades."
    )
    args_schema: Type[BaseModel] = TradeAttributionInput
    database_manager: Optional[DatabaseManager] = None
    session_manager: Optional[SessionManager] = None

    def __init__(
            self,
            database_manager: Optional[DatabaseManager] = None,
            session_manager: Optional[SessionManager] = None,
    ):
        super().__init__(database_manager=database_manager, session_manager=session_manager)

    def _run(  # pylint: disable=arguments-differ,too-many-return-statements
            self,
            dimension: str = "strategy",
            ticker_symbol: Optional[str] = None,
            lookback_days: int = 30,
    ) -> str:
        self.app_logger.info(
            f"Trade attribution requested (dim={dimension}, symbol={ticker_symbol}, lookback={lookback_days}d)"
        )
        trades = self._gather_trades(ticker_symbol=ticker_symbol, lookback_days=lookback_days)
        if not trades:
            return "No completed trades found for attribution analysis in the specified period."

        normalized_dim = dimension.strip().lower()
        if normalized_dim == "commit":
            attr = TradeAttributionService.attribute_by_commit(trades)
            return self._format_attribution_dict("Commit Hash", attr)
        if normalized_dim == "symbol":
            attr = TradeAttributionService.attribute_by_symbol(trades)
            return self._format_attribution_dict("Ticker Symbol", attr)
        if normalized_dim == "regime":
            attr = TradeAttributionService.attribute_by_regime(trades)
            return self._format_attribution_dict("Market Regime", attr)
        if normalized_dim in ("strategy_by_regime", "regime_strategy"):
            return self._format_strategy_by_regime(trades, lookback_days)
        if normalized_dim == "overall":
            metrics = TradeAttributionService.calculate_metrics(trades)
            return self._format_single_attribution("Overall Performance", metrics)

        return self._format_reconciled_strategy_attribution(trades, lookback_days)

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
                orders = repo.get_all()
                completed = [o for o in orders if o.status is not None and o.status.value == "COMPLETED"]
                symbols = list({o.ticker_symbol for o in completed})

        all_trades: list[Trade] = []
        for symbol in symbols:
            symbol_orders = [o for o in orders if o.ticker_symbol == symbol]
            matched = AssetPerformanceService.extract_trades(
                ticker_symbol=symbol,
                orders=symbol_orders,
            )
            all_trades.extend(matched)
        return all_trades

    @classmethod
    def _format_attribution_dict(cls, group_name: str, attribution: dict[str, AttributionMetrics]) -> str:
        if not attribution:
            return "No attribution data available."

        lines = [f"Trade Attribution Breakdown by {group_name}:"]
        for key, metrics in sorted(attribution.items()):
            lines.append(f"\n[{group_name}: {key}]")
            lines.append(cls._format_metrics_block(metrics))
        return "\n".join(lines)

    @classmethod
    def _format_single_attribution(cls, title: str, metrics: AttributionMetrics) -> str:
        lines = [f"[{title}]", cls._format_metrics_block(metrics)]
        return "\n".join(lines)

    @staticmethod
    def _fmt_signed_usd(val: Decimal) -> str:
        sign = "+" if val >= Decimal("0") else "-"
        return f"{sign}${abs(val):.2f}"

    @classmethod
    def _format_reconciled_strategy_attribution(cls, trades: list[Trade], lookback_days: int) -> str:
        overall = TradeAttributionService.calculate_metrics(trades)
        prop_attr = TradeAttributionService.attribute_by_strategy_proportional(trades)
        part_attr = TradeAttributionService.attribute_by_strategy(trades)
        reconciled_sum = sum((m.net_pnl for m in prop_attr.values()), Decimal("0"))
        reconciled = abs(reconciled_sum - overall.net_pnl) <= Decimal("0.01")

        lines = [
            f"Trade Attribution Breakdown by Strategy (Window: {lookback_days}d UTC, Basis: Realized Closed Trades):",
            f"Reconciled Portfolio Realized Net PnL: {cls._fmt_signed_usd(overall.net_pnl)} "
            f"(Proportional Strategy Sum: {cls._fmt_signed_usd(reconciled_sum)}, "
            f"Reconciled: {reconciled}, Total Trades: {overall.total_trades})",
        ]
        for key in sorted(prop_attr.keys()):
            prop_m = prop_attr[key]
            part_m = part_attr.get(key)
            unadjusted_note = (
                f" | Unadjusted Participation Net PnL: {cls._fmt_signed_usd(part_m.net_pnl)} "
                f"across {part_m.total_trades} trade(s)"
                if part_m is not None else ""
            )
            lines.append(
                f"\n[Strategy: {key}] (Proportional Net PnL: "
                f"{cls._fmt_signed_usd(prop_m.net_pnl)}{unadjusted_note})"
            )
            lines.append(cls._format_metrics_block(prop_m))
        return "\n".join(lines)

    @classmethod
    def _format_strategy_by_regime(cls, trades: list[Trade], lookback_days: int) -> str:
        overall = TradeAttributionService.calculate_metrics(trades)
        by_regime = TradeAttributionService.attribute_strategy_by_regime(trades)
        regime_totals = TradeAttributionService.attribute_by_regime(trades)
        lines = [
            f"Strategy Performance by Market Regime (Window: {lookback_days}d UTC, "
            f"Baseline Net PnL: {cls._fmt_signed_usd(overall.net_pnl)}, "
            f"Baseline Win Rate: {overall.win_rate_pct:.1f}%, Total Sample Size: {overall.total_trades} trades):"
        ]
        for regime, r_metrics in sorted(regime_totals.items()):
            low_sample = " [LOW SAMPLE SIZE]" if r_metrics.total_trades < 5 else ""
            lines.append(
                f"\n=== Regime: {regime} (Sample Size: n={r_metrics.total_trades}, "
                f"Regime Net PnL: {cls._fmt_signed_usd(r_metrics.net_pnl)}, "
                f"Win Rate: {r_metrics.win_rate_pct:.1f}%){low_sample} ==="
            )
        for strat, regimes in sorted(by_regime.items()):
            lines.append(f"\n[Strategy: {strat}]")
            for regime, m in sorted(regimes.items()):
                low_sample = " (Warning: Small Sample Size n<5)" if m.total_trades < 5 else ""
                lines.append(
                    f"  - Regime {regime}: Net PnL={cls._fmt_signed_usd(m.net_pnl)} | Win Rate={m.win_rate_pct:.1f}% | "
                    f"Sample Size n={m.total_trades} | Avg Return={m.avg_return_pct:+.2f}%{low_sample}"
                )
        return "\n".join(lines)

    @classmethod
    def _format_metrics_block(cls, metrics: AttributionMetrics) -> str:
        return (
            f"  Trades: {metrics.total_trades} "
            f"(Wins: {metrics.winning_trades}, Losses: {metrics.losing_trades}, "
            f"Break-even: {metrics.break_even_trades})\n"
            f"  Win Rate: {metrics.win_rate_pct:.1f}%\n"
            f"  Net PnL: {cls._fmt_signed_usd(metrics.net_pnl)} "
            f"(Gross: {cls._fmt_signed_usd(metrics.gross_pnl)}, Fees: ${metrics.total_fees:.4f}, "
            f"Slippage: ${metrics.total_slippage:.4f})\n"
            f"  Profit Factor: {metrics.profit_factor:.2f}\n"
            f"  Avg Return: {metrics.avg_return_pct:+.2f}%\n"
            f"  Avg Duration: {metrics.avg_duration_seconds:.1f}s\n"
            f"  Max Win: {cls._fmt_signed_usd(metrics.max_win)} | Max Loss: {cls._fmt_signed_usd(metrics.max_loss)}"
        )
