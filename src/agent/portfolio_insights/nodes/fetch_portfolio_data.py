from __future__ import annotations

from src.agent.portfolio_insights.models import PortfolioQueryIntent
from src.agent.portfolio_insights.state import PortfolioInsightsState
from src.core.interfaces.llm_adapter import LlmAdapter
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class FetchPortfolioDataNode(ApplicationLoggingMixin):
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(self, state: PortfolioInsightsState) -> dict:
        intent = state.get("portfolio_query") or PortfolioQueryIntent()
        results: list[str] = []

        portfolio_tool = self._llm.get_tool("portfolio_summary")
        if portfolio_tool is not None:
            try:
                tool_args = {}
                if intent.quote_currency:
                    tool_args["quote_currency"] = intent.quote_currency
                if intent.exchange:
                    tool_args["exchange"] = intent.exchange
                data = portfolio_tool.invoke(tool_args)
                results.append(str(data))
            except Exception as exc:  # pylint: disable=broad-except
                self.app_logger.error(f"Error fetching portfolio summary: {exc}")
                results.append(f"Error fetching portfolio summary: {exc}")

        exchange_tool = self._llm.get_tool("exchange_read_api")
        if exchange_tool is not None and intent.exchange:
            try:
                if intent.target_asset:
                    ticker_data = exchange_tool.invoke({
                        "operation": "get_ticker",
                        "exchange": intent.exchange,
                        "ticker_symbol": intent.target_asset,
                    })
                    results.append(f"Exchange Ticker ({intent.target_asset}):\n{ticker_data}")
            except Exception as exc:  # pylint: disable=broad-except
                self.app_logger.error(f"Error fetching exchange ticker: {exc}")

        if not results:
            return {"portfolio_data": "Portfolio summary tool is not available."}

        return {"portfolio_data": "\n\n".join(results)}
