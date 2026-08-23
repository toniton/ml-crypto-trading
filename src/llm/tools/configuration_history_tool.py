from __future__ import annotations

from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.vcs.application.service import VCSService


class ConfigurationHistoryInput(BaseModel):
    limit: int = Field(
        default=20,
        description="Maximum number of most recent configuration commits to return.",
    )


class ConfigurationHistoryTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_configuration_history"
    description: str = (
        "Returns the recent configuration change history (commits) with author, message, and timestamp."
    )
    args_schema: Type[BaseModel] = ConfigurationHistoryInput
    vcs: VCSService

    def __init__(self, vcs: VCSService):
        super().__init__(vcs=vcs)

    def _run(self, limit: int = 20) -> str:  # pylint: disable=arguments-differ
        try:
            commits = self.vcs.log("HEAD", limit=limit)
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.error(f"Error fetching configuration history: {exc}")
            return f"Error fetching configuration history: {exc}"

        self.app_logger.info(f"Configuration history (limit={limit}) requested by LLM.")

        if not commits:
            return "No configuration history available."

        lines = [f"Configuration history (last {len(commits)} commits):"]
        for commit in commits:
            timestamp = commit.created_at.isoformat() if commit.created_at else "unknown"
            lines.append(f"- {commit.hash[:8]} {timestamp} {commit.author}: {commit.message}")
        return "\n".join(lines)
