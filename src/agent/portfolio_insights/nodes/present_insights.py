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
                f"- **Total Mark-to-Market Equity:** `${FormatHelper.format_decimal(s.total_equity)} {s.quote_currency}`",
                f"- **Available Cash / Reserved Cash:** `${FormatHelper.format_decimal(s.available_cash)}` / `${FormatHelper.format_decimal(s.reserved_cash)}`",
                f"- **Drawdown from Peak:** `{FormatHelper.format_decimal(s.current_drawdown_pct)}%` (Peak: `${FormatHelper.format_decimal(s.peak_equity)}`)",
                "",
            ]

            if s.allocations:
                lines.append("| Asset | Quantity | Mark Price | Position Value | Portfolio Weight |")
                lines.append("| :--- | :--- | :--- | :--- | :--- |")
                for a in s.allocations:
                    lines.append(
                        f"| **{a.ticker_symbol}** | {FormatHelper.format_decimal(a.quantity)} | ${FormatHelper.format_decimal(a.mark_price)} "
                        f"| ${FormatHelper.format_decimal(a.position_value)} | `{FormatHelper.format_decimal(a.weight_pct)}%` |"
                    )
                lines.append("")

            if s.risk_warnings:
                lines.append("> [!WARNING]")
                for w in s.risk_warnings:
                    lines.append(f"> - {w}")
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
