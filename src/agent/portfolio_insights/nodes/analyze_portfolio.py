from __future__ import annotations

from src.agent.portfolio_insights.models import PortfolioAnalysisResult
from src.agent.portfolio_insights.prompts import ANALYZE_PORTFOLIO_PROMPT
from src.agent.portfolio_insights.state import PortfolioInsightsState
from src.core.interfaces.llm_adapter import LlmAdapter


class AnalyzePortfolioNode:
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(self, state: PortfolioInsightsState) -> dict:
        portfolio_data = state.get("portfolio_data") or "No portfolio data available."

        if not portfolio_data or "not available" in portfolio_data.lower() or "no active quote portfolios" in portfolio_data.lower():
            return {
                "analysis": PortfolioAnalysisResult(
                    snapshots=[],
                    overall_health="HEALTHY",
                    findings=["No active quote portfolios currently registered in the risk manager."],
                    recommendations=["Ensure assets and exchange connections are enabled to initialize portfolio tracking."],
                )
            }

        prompt = (
            f"USER PROMPT:\n{state.get('user_prompt', '')}\n\n"
            f"RETRIEVED PORTFOLIO DATA:\n{portfolio_data}"
        )

        try:
            analysis: PortfolioAnalysisResult = self._llm.generate_structured(
                schema=PortfolioAnalysisResult,
                prompt=prompt,
                system_prompt=ANALYZE_PORTFOLIO_PROMPT,
            )
            return {"analysis": analysis}
        except Exception:
            analysis_text = self._llm.generate(prompt)
            return {
                "analysis": PortfolioAnalysisResult(
                    findings=[analysis_text],
                    overall_health="HEALTHY",
                )
            }
