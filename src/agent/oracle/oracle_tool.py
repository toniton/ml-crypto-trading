from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.agent.oracle.oracle_service import OracleService
from src.agent.oracle.oracle_summary import OracleSummary
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class _NoArgs(BaseModel):
    pass


class TradingSummaryInput(BaseModel):
    days: Optional[int] = Field(
        default=None,
        description=(
            "Number of past days to query historical summaries and events (e.g. 1 for last 24h, "
            "7 for last week). If omitted, returns the latest trading summary."
        ),
    )
    symbol: Optional[str] = Field(
        default=None,
        description="Optional asset symbol (e.g. 'BTC_USD') to filter historical summaries.",
    )


def _format_summary(summary: Optional[OracleSummary]) -> str:
    if summary is None:
        return "No Oracle trading summary available."
    return (
        f"Oracle trading summary (session={summary.session_id}, "
        f"symbol={summary.symbol}, generated_at={summary.generated_at.isoformat()}):\n"
        f"  Market state: {summary.market_state}\n"
        f"  Trading state: {summary.trading_state}\n"
        f"  Risk state: {summary.risk_state}\n"
        f"  Summary:\n{summary.summary}"
    )


class GetTradingSummaryTool(BaseTool, ApplicationLoggingMixin):
    """Returns trading summaries (latest or historical across days)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_trading_summary"
    description: str = (
        "Return Oracle trading summaries. Specify 'days' (e.g. 1, 3, 7) to retrieve "
        "historical summaries and trading events over a past time window, and optionally "
        "'symbol' to filter by asset. If 'days' is omitted, returns the latest summary."
    )
    args_schema: Type[BaseModel] = TradingSummaryInput
    oracle_service: OracleService
    timeline_projector: Optional[Any] = None

    def __init__(
            self,
            oracle_service: OracleService,
            timeline_projector: Optional[Any] = None,
    ):
        super().__init__(
            oracle_service=oracle_service,
            timeline_projector=timeline_projector,
        )

    def _run(  # pylint: disable=arguments-differ
            self,
            days: Optional[int] = None,
            symbol: Optional[str] = None,
    ) -> str:
        self.app_logger.info(
            "Trading summary requested by LLM (days=%s, symbol=%s).",
            days,
            symbol,
        )
        if days is not None and days > 0 and self.timeline_projector is not None:
            return self._query_historical_summaries(days, symbol)

        summary = self.oracle_service.get_latest_summary()
        if summary is None:
            summary = self.oracle_service.summarize()
        return _format_summary(summary)

    def _query_historical_summaries(self, days: int, symbol: Optional[str] = None) -> str:
        items = self.timeline_projector.list_items(
            category="AGENT",
            entity_type="ASSET" if symbol else None,
            entity_id=symbol if symbol else None,
            days=days,
            limit=50,
        )
        if not items:
            latest = self.oracle_service.get_latest_summary() or self.oracle_service.summarize()
            suffix = f" for {symbol}." if symbol else "."
            return (
                f"No historical Oracle summaries found in the past {days} day(s){suffix}\n\n"
                f"Latest available summary:\n{_format_summary(latest)}"
            )

        header = (
                f"Found {len(items)} Oracle trading summary event(s) over the last {days} day(s)"
                + (f" for {symbol}:" if symbol else ":")
        )
        lines = [header, ""]
        for idx, item in enumerate(items, 1):
            lines.extend(self._format_historical_item(idx, item))
            lines.append("")

        return "\n".join(lines).strip()

    @staticmethod
    def _format_historical_item(idx: int, item: dict) -> list[str]:
        ts = item.get("timestamp", "unknown")
        title = item.get("title", "Oracle Summary")
        meta = item.get("metadata", {})
        sym = meta.get("symbol") or "ALL"
        m_state = meta.get("market_state", "N/A")
        t_state = meta.get("trading_state", "N/A")
        r_state = meta.get("risk_state", "N/A")
        full_summary = meta.get("summary") or item.get("summary", "")

        return [
            f"[{idx}] {ts} - {title} (Asset: {sym})",
            f"    States: Market={m_state}, Trading={t_state}, Risk={r_state}",
            f"    Summary:\n    {full_summary.strip()}",
        ]


class AnalyzeTradingStateTool(BaseTool, ApplicationLoggingMixin):
    """Explicitly asks the Oracle to produce a fresh analysis of the current state."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "analyze_trading_state"
    description: str = (
        "Generate a fresh Oracle analysis of the current accumulated trading state "
        "by invoking the LLM."
    )
    args_schema: Type[BaseModel] = _NoArgs
    oracle_service: OracleService

    def __init__(self, oracle_service: OracleService):
        super().__init__(oracle_service=oracle_service)

    def _run(self) -> str:  # pylint: disable=arguments-differ
        self.app_logger.info("Fresh trading state analysis requested by LLM.")
        return _format_summary(self.oracle_service.summarize())
