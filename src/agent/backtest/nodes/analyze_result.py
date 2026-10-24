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
        market_series = getattr(result, "market_series", [])
        fills = getattr(result, "fills", [])
        if len(market_series) == 0:
            notes.append("No market data was available for the requested window.")
        elif len(market_series) <= 1:
            notes.append(
                "Insufficient historical market observations (1 data point); "
                "cannot establish historical performance."
            )
        elif len(market_series) < 20:
            notes.append("Few market observations; treat conclusions with caution.")

        if len(fills) == 0:
            notes.append("No orders were filled.")

        return {
            "quality": BacktestQuality(
                sufficient_evidence=len(fills) > 0 and len(market_series) > 1,
                notes=notes,
            )
        }
