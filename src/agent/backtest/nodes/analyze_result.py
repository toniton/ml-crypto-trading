from __future__ import annotations

from src.agent.backtest.models import BacktestQuality
from src.agent.backtest.state import BacktestAgentState


class AnalyzeResultNode:
    def __call__(self, state: BacktestAgentState) -> dict:
        result = state.get("result")
        if result is None:
            return {
                "quality": BacktestQuality(
                    sufficient_evidence=False,
                    notes=["No result was produced."],
                )
            }

        notes: list[str] = []
        if len(result.market_series) == 0:
            notes.append("No market data was available for the requested window.")
        if len(result.fills) == 0:
            notes.append("No orders were filled.")
        if len(result.market_series) < 20:
            notes.append("Few market observations; treat conclusions with caution.")

        return {
            "quality": BacktestQuality(
                sufficient_evidence=len(result.fills) > 0,
                notes=notes,
            )
        }
