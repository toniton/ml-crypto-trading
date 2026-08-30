from __future__ import annotations

from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict

from src.agent.oracle.oracle_service import OracleService
from src.agent.oracle.oracle_summary import OracleSummary
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class _NoArgs(BaseModel):
    pass


def _format_summary(summary: OracleSummary) -> str:
    return (
        f"Oracle trading summary (session={summary.session_id}, "
        f"symbol={summary.symbol}, generated_at={summary.generated_at.isoformat()}):\n"
        f"  Market state: {summary.market_state}\n"
        f"  Trading state: {summary.trading_state}\n"
        f"  Risk state: {summary.risk_state}\n"
        f"  Summary:\n{summary.summary}"
    )


class GetTradingSummaryTool(BaseTool, ApplicationLoggingMixin):
    """Returns the latest Oracle summary without invoking the LLM if one exists."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_trading_summary"
    description: str = (
        "Return the most recently generated Oracle trading summary. If none has been "
        "generated yet, a fresh summary is produced from accumulated trading events."
    )
    args_schema: Type[BaseModel] = _NoArgs
    oracle_service: OracleService

    def __init__(self, oracle_service: OracleService):
        super().__init__(oracle_service=oracle_service)

    def _run(self) -> str:  # pylint: disable=arguments-differ
        summary = self.oracle_service.get_latest_summary()
        if summary is None:
            summary = self.oracle_service.summarize()
        self.app_logger.info("Trading summary requested by LLM.")
        return _format_summary(summary)


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
