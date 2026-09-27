from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from src.agent.portfolio_insights.graph import PortfolioInsightsGraph
from src.agent.portfolio_insights.models import (
    AssetAllocation,
    PortfolioAnalysisResult,
    PortfolioQueryIntent,
    QuotePortfolioSnapshot,
)
from src.agent.portfolio_insights.nodes.analyze_portfolio import AnalyzePortfolioNode
from src.agent.portfolio_insights.nodes.fetch_portfolio_data import FetchPortfolioDataNode
from src.agent.portfolio_insights.nodes.present_insights import PresentInsightsNode
from src.agent.portfolio_insights.nodes.understand_portfolio_query import UnderstandPortfolioQueryNode
from src.core.interfaces.llm_adapter import LlmAdapter
from src.llm.tools.portfolio_summary_tool import PortfolioSummaryTool
from src.trading.protection.portfolio_risk_manager import PortfolioRiskManager


def _mock_llm(structured_returns: list | None = None, tools: dict | None = None) -> MagicMock:
    llm = MagicMock(spec=LlmAdapter)
    if structured_returns:
        llm.generate_structured.side_effect = structured_returns
    tools_dict = tools or {}
    llm.get_tool.side_effect = lambda name: tools_dict.get(name)
    return llm


def _make_sample_risk_manager() -> PortfolioRiskManager:
    risk_mgr = PortfolioRiskManager(
        max_portfolio_drawdown=Decimal("10.0"),
        max_asset_concentration=Decimal("50.0"),
    )
    portfolio = risk_mgr.get_portfolio("CRYPTO_DOT_COM", "USD")
    portfolio.update_cash(Decimal("2000.00"))
    portfolio.reserve_cash("order-1", Decimal("500.00"))
    portfolio.update_asset_position("BTC_USD", Decimal("0.10"))
    portfolio.update_asset_mark_price("BTC_USD", Decimal("60000.00"))
    portfolio.update_asset_position("ETH_USD", Decimal("1.0"))
    portfolio.update_asset_mark_price("ETH_USD", Decimal("3000.00"))
    portfolio.peak_equity = Decimal("12000.00")
    return risk_mgr


class TestUnderstandPortfolioQueryNode:
    def test_parses_portfolio_query(self):
        expected = PortfolioQueryIntent(
            quote_currency="USD",
            exchange="CRYPTO_DOT_COM",
            focus_areas=["drawdown", "concentration"],
        )
        llm = _mock_llm([expected])
        node = UnderstandPortfolioQueryNode(llm)

        state = {"user_prompt": "Check my USD portfolio on Crypto.com for drawdown risks"}
        result = node(state)

        assert result["portfolio_query"].quote_currency == "USD"
        assert result["portfolio_query"].exchange == "CRYPTO_DOT_COM"
        assert "drawdown" in result["portfolio_query"].focus_areas


class TestFetchPortfolioDataNode:
    def test_fetches_portfolio_data_via_tool(self):
        risk_mgr = _make_sample_risk_manager()
        summary_tool = PortfolioSummaryTool(portfolio_risk_manager=risk_mgr)
        llm = _mock_llm(tools={"portfolio_summary": summary_tool})

        node = FetchPortfolioDataNode(llm)

        state = {
            "portfolio_query": PortfolioQueryIntent(quote_currency="USD"),
        }
        result = node(state)
        portfolio_data = result["portfolio_data"]

        assert "Portfolio [CRYPTO_DOT_COM / USD]" in portfolio_data
        assert "Total Mark-to-Market Equity: $11000 USD" in portfolio_data
        assert "Available Cash:             $1500 USD" in portfolio_data

    def test_fetch_when_tools_unavailable(self):
        llm = _mock_llm(tools={})
        node = FetchPortfolioDataNode(llm)

        state = {"portfolio_query": PortfolioQueryIntent()}
        result = node(state)
        assert "Portfolio summary tool is not available" in result["portfolio_data"]


class TestAnalyzePortfolioNode:
    def test_analyze_portfolio_with_data(self):
        expected_analysis = PortfolioAnalysisResult(
            overall_health="WARNING",
            findings=["BTC concentration is 54.5% exceeding 50% limit.", "Drawdown is 8.3% within 10% limit."],
            recommendations=["Consider taking partial profits on BTC_USD to reduce concentration."],
        )
        llm = _mock_llm([expected_analysis])
        node = AnalyzePortfolioNode(llm)

        state = {
            "user_prompt": "Analyze my portfolio risks",
            "portfolio_data": "Portfolio [CRYPTO_DOT_COM / USD]:\n  Total Mark-to-Market Equity: $11,000.00 USD",
        }

        result = node(state)
        analysis = result["analysis"]
        assert analysis.overall_health == "WARNING"
        assert len(analysis.findings) == 2

    def test_analyze_portfolio_empty_data_fallback(self):
        llm = _mock_llm([])
        node = AnalyzePortfolioNode(llm)

        state = {
            "user_prompt": "Analyze portfolio",
            "portfolio_data": "No active quote portfolios registered in the portfolio risk manager.",
        }

        result = node(state)
        analysis = result["analysis"]
        assert analysis.overall_health == "HEALTHY"
        assert "No active quote portfolios" in analysis.findings[0]


class TestPresentInsightsNode:
    def test_presents_markdown_blocks(self):
        node = PresentInsightsNode()
        snapshot = QuotePortfolioSnapshot(
            exchange="CRYPTO_DOT_COM",
            quote_currency="USD",
            cash_balance=Decimal("2000.00"),
            reserved_cash=Decimal("0.00"),
            available_cash=Decimal("2000.00"),
            total_equity=Decimal("5000.00"),
            peak_equity=Decimal("5000.00"),
            current_drawdown_pct=Decimal("0.0"),
            allocations=[
                AssetAllocation(
                    ticker_symbol="BTC_USD",
                    quantity=Decimal("0.05"),
                    mark_price=Decimal("60000.00"),
                    position_value=Decimal("3000.00"),
                    weight_pct=Decimal("60.0"),
                )
            ],
        )
        analysis = PortfolioAnalysisResult(
            overall_health="HEALTHY",
            findings=["Portfolio is 40% cash and 60% BTC."],
            recommendations=["Maintain existing allocation."],
            snapshots=[snapshot],
        )

        state = {"analysis": analysis}
        result = node(state)
        blocks = result["presentation"].blocks

        assert len(blocks) == 3
        assert "Portfolio Health & Insights (🟢 **HEALTHY**)" in blocks[0].content
        assert "| **BTC_USD** |" in blocks[1].content
        assert "Maintain existing allocation." in blocks[2].content


class TestPortfolioInsightsGraphEndToEnd:
    def test_full_graph_execution(self):
        risk_mgr = _make_sample_risk_manager()
        summary_tool = PortfolioSummaryTool(portfolio_risk_manager=risk_mgr)

        intent = PortfolioQueryIntent(quote_currency="USD")
        analysis = PortfolioAnalysisResult(
            overall_health="HEALTHY",
            findings=["Everything is operating normally."],
            recommendations=["No action needed."],
        )
        llm = _mock_llm(
            structured_returns=[intent, analysis],
            tools={"portfolio_summary": summary_tool},
        )

        graph = PortfolioInsightsGraph(llm=llm).build()

        state = graph.invoke({"user_prompt": "Give me a full portfolio review"})
        assert "presentation" in state
        assert len(state["presentation"].blocks) >= 2
