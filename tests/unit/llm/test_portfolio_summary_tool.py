from decimal import Decimal
from unittest.mock import MagicMock

from src.llm.tools.portfolio_summary_tool import PortfolioSummaryTool
from src.trading.protection.portfolio_risk_manager import PortfolioRiskManager
from src.trading.protection.quote_portfolio import QuotePortfolio


def test_portfolio_summary_tool():
    risk_mgr = MagicMock(spec=PortfolioRiskManager)
    risk_mgr.max_portfolio_drawdown = Decimal("15.0")
    risk_mgr.max_asset_concentration = Decimal("40.0")

    portfolio = QuotePortfolio(exchange="CRYPTO_DOT_COM", quote_currency="USD")
    portfolio.update_cash(Decimal("1000.00"))
    portfolio.reserve_cash("order-1", Decimal("200.00"))
    portfolio.update_asset_position("BTC_USD", Decimal("0.05"))
    portfolio.update_asset_mark_price("BTC_USD", Decimal("60000.00"))
    portfolio.peak_equity = Decimal("4500.00")

    risk_mgr.portfolios = {("CRYPTO_DOT_COM", "USD"): portfolio}

    tool = PortfolioSummaryTool(portfolio_risk_manager=risk_mgr)
    result = tool._run()

    assert "Portfolio [CRYPTO_DOT_COM / USD]:" in result
    assert "Total Mark-to-Market Equity: $4000 USD" in result
    assert "Available Cash:             $800 USD" in result
    assert "BTC_USD: 0.05 units @ $60000 = $3000 USD (75% of portfolio)" in result
    assert "Max Concentration Limit:    40%" in result
    assert "Limit: 15%" in result


def test_portfolio_summary_tool_empty():
    risk_mgr = MagicMock(spec=PortfolioRiskManager)
    risk_mgr.portfolios = {}

    tool = PortfolioSummaryTool(portfolio_risk_manager=risk_mgr)
    result = tool._run()
    assert "No active quote portfolios registered" in result
