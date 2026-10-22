from __future__ import annotations

from decimal import Decimal

from src.agent.configuration.models import MarkdownBlock
from src.agent.portfolio_insights.models import PortfolioAnalysisResult, PortfolioInsightsPresentation
from src.agent.portfolio_insights.state import PortfolioInsightsState
from src.trading.helpers.format_helper import FormatHelper


class PresentInsightsNode:
    def __call__(self, state: PortfolioInsightsState) -> dict:
        analysis: PortfolioAnalysisResult = (
            state["analysis"]
            if "analysis" in state and state["analysis"] is not None
            else PortfolioAnalysisResult()
        )
        blocks = self._build_blocks(analysis)
        presentation = PortfolioInsightsPresentation(blocks=blocks)
        return {"presentation": presentation}

    @staticmethod
    def _fmt_pct(value: Decimal | float) -> str:
        rounded = Decimal(str(value)).quantize(Decimal("0.01"))
        return FormatHelper.format_decimal(rounded)

    @staticmethod
    def _fmt_currency(value: Decimal | float) -> str:
        dec = Decimal(str(value))
        if dec.as_tuple().exponent < -4:
            dec = dec.quantize(Decimal("0.0001"))
        return FormatHelper.format_decimal(dec)

    def _build_blocks(self, analysis: PortfolioAnalysisResult) -> list[MarkdownBlock]:
        blocks: list[MarkdownBlock] = []

        # 1. Executive Summary & Health Badge
        badge = "🟢 **HEALTHY**" if analysis.overall_health == "HEALTHY" else (
            "🟡 **WARNING**" if analysis.overall_health == "WARNING" else "🔴 **CRITICAL**"
        )
        summary_lines = [
            f"### Portfolio Health & Insights ({badge})",
            "",
        ]
        if analysis.findings:
            summary_lines.append("**Key Findings:**")
            for f in analysis.findings:
                summary_lines.append(f"- {f}")
            summary_lines.append("")

        blocks.append(MarkdownBlock(content="\n".join(summary_lines)))

        # 2. Portfolio Breakdown Tables
        for s in analysis.snapshots:
            lines = [
                f"#### Portfolio: `{s.exchange}` ({s.quote_currency})",
                "",
                f"- **Total Mark-to-Market Equity:** `${self._fmt_currency(s.total_equity)} {s.quote_currency}`",
                (
                    f"- **Available Cash / Reserved Cash:** "
                    f"`${self._fmt_currency(s.available_cash)}` / `${self._fmt_currency(s.reserved_cash)}`"
                ),
                (
                    f"- **Drawdown from Peak:** `{self._fmt_pct(s.current_drawdown_pct)}%` "
                    f"(Peak: `${self._fmt_currency(s.peak_equity)}`)"
                ),
                "",
            ]

            if s.allocations:
                lines.append("| Asset | Quantity | Mark Price | Position Value | Portfolio Weight |")
                lines.append("| :--- | :--- | :--- | :--- | :--- |")
                for a in s.allocations:
                    lines.append(
                        f"| **{a.ticker_symbol}** | {FormatHelper.format_decimal(a.quantity)} "
                        f"| ${FormatHelper.format_decimal(a.mark_price)} "
                        f"| ${self._fmt_currency(a.position_value)} | `{self._fmt_pct(a.weight_pct)}%` |"
                    )
                lines.append("")

            if s.risk_warnings:
                lines.append("**⚠️ Risk Warnings:**")
                for w in s.risk_warnings:
                    lines.append(f"- {w}")
                lines.append("")

            blocks.append(MarkdownBlock(content="\n".join(lines)))

        # 3. Actionable Recommendations
        if analysis.recommendations:
            rec_lines = [
                "### Recommendations & Next Steps",
                "",
            ]
            for r in analysis.recommendations:
                rec_lines.append(f"1. {r}")
            blocks.append(MarkdownBlock(content="\n".join(rec_lines)))

        return blocks
