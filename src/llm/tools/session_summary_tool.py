from __future__ import annotations

from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict

from src.llm.tools.trading_context_tool import format_decimal
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.session.session_manager import SessionManager


class SessionSummaryInput(BaseModel):
    pass


class SessionSummaryTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_session_summary"
    description: str = (
        "Returns a summary of the current trading session: id, duration, and per-asset balances and activity."
    )
    args_schema: Type[BaseModel] = SessionSummaryInput
    session_manager: SessionManager

    def __init__(self, session_manager: SessionManager):
        super().__init__(session_manager=session_manager)

    def _run(self) -> str:  # pylint: disable=arguments-differ
        session = self.session_manager.current_session
        if not session:
            return "Error: No active trading session."

        self.app_logger.info("Session summary requested by LLM.")
        summary = self.session_manager.get_session_summary(session)
        lines = [
            f"Session summary for {summary['session_id']}:",
            f"  Running: {summary['is_running']}",
            f"  Duration: {summary['duration']}s",
            f"  Commit hash: {summary['commit_hash']}",
            f"  Assets: {summary['assets']}",
        ]
        for ctx in summary["contexts"].values():
            lines.append(
                f"  - {ctx['ticker_symbol']} ({ctx['exchange']}): "
                f"starting={format_decimal(ctx['starting_balance'])}, "
                f"available={format_decimal(ctx['available_balance'])}, "
                f"closing={format_decimal(ctx['closing_balance'])}, "
                f"buys={ctx['buy_count']}"
            )
        return "\n".join(lines)
