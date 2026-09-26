from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Type

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
    database_manager: Optional[Any] = None
    session_manager: Optional[Any] = None

    def __init__(
            self,
            database_manager: Optional[DatabaseManager] = None,
            session_manager: Optional[Any] = None,
    ):
        super().__init__(database_manager=database_manager, session_manager=session_manager)

    def _run(  # pylint: disable=arguments-differ
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
        if normalized_dim == "overall":
            metrics = TradeAttributionService.calculate_metrics(trades)
            return self._format_single_attribution("Overall Performance", metrics)

        attr = TradeAttributionService.attribute_by_strategy(trades)
        return self._format_attribution_dict("Strategy", attr)

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
    def _format_metrics_block(metrics: AttributionMetrics) -> str:
        return (
            f"  Trades: {metrics.total_trades} "
            f"(Wins: {metrics.winning_trades}, Losses: {metrics.losing_trades}, "
            f"Break-even: {metrics.break_even_trades})\n"
            f"  Win Rate: {metrics.win_rate_pct:.1f}%\n"
            f"  Net PnL: ${metrics.net_pnl:+.2f} "
            f"(Gross: ${metrics.gross_pnl:+.2f}, Fees: ${metrics.total_fees:.4f}, "
            f"Slippage: ${metrics.total_slippage:.4f})\n"
            f"  Profit Factor: {metrics.profit_factor:.2f}\n"
            f"  Avg Return: {metrics.avg_return_pct:+.2f}%\n"
            f"  Avg Duration: {metrics.avg_duration_seconds:.1f}s\n"
            f"  Max Win: ${metrics.max_win:+.2f} | Max Loss: ${metrics.max_loss:+.2f}"
        )
