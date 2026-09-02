from __future__ import annotations

from src.agent.backtest.models import (
    BacktestPresentation,
    BacktestQuality,
    BacktestValidation,
)
from src.agent.backtest.state import BacktestAgentState
from src.agent.configuration.models import MarkdownBlock
from src.backtest.domain.metrics import BacktestSummary


class PresentResultNode:
    def __call__(self, state: BacktestAgentState) -> dict:
        content = self._render(state)
        return {
            "presentation": BacktestPresentation(blocks=[MarkdownBlock.from_text(content)])
        }

    @staticmethod
    def _render(state: BacktestAgentState) -> str:
        if state.get("error"):
            return f"Backtest failed: {state['error']}"

        validation: BacktestValidation | None = state.get("validation")
        if validation and not validation.valid:
            lines = ["I can't run that backtest yet:"]
            lines.extend(f"- {error}" for error in validation.errors)
            return "\n".join(lines)

        summary: BacktestSummary | None = state.get("summary")
        quality: BacktestQuality | None = state.get("quality")
        parts: list[str] = []
        if summary is not None:
            parts.append(PresentResultNode._format_summary(summary))
        if quality is not None:
            notes = PresentResultNode._format_quality(quality)
            if notes:
                parts.append(notes)
        return "\n\n".join(parts)

    @staticmethod
    def _format_summary(summary: BacktestSummary) -> str:
        return (
            f"Backtest {summary.ticker_symbol} (session {summary.session_id}):\n"
            f"- Status: {summary.status}\n"
            f"- Return: {summary.return_pct:.4f}%\n"
            f"- PnL: {summary.absolute_pnl:.4f}\n"
            f"- Max drawdown: {summary.max_drawdown_pct:.4f}%\n"
            f"- Round trips: {summary.round_trips}\n"
            f"- Fills: {summary.orders_filled}\n"
            f"- Cancelled: {summary.orders_cancelled}"
        )

    @staticmethod
    def _format_quality(quality: BacktestQuality) -> str:
        if not quality.notes:
            return ""
        return "Notes:\n" + "\n".join(f"- {note}" for note in quality.notes)
