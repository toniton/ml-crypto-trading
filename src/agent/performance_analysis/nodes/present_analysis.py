from __future__ import annotations

from src.agent.configuration.models import MarkdownBlock
from src.agent.performance_analysis.models import AnalyticsPresentation
from src.agent.performance_analysis.state import PerformanceAnalysisState


class PresentAnalysisNode:
    def __call__(self, state: PerformanceAnalysisState) -> dict:
        content = (
                state.get("analysis_summary")
                or state.get("metric_data")
                or "No analytical data available."
        )
        presentation = AnalyticsPresentation(
            blocks=[MarkdownBlock.from_text(content)]
        )
        return {"presentation": presentation}
