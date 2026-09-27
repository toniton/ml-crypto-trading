from __future__ import annotations

from src.agent.portfolio_insights.models import PortfolioQueryIntent
from src.agent.portfolio_insights.state import PortfolioInsightsState
from src.core.interfaces.llm_adapter import LlmAdapter
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class FetchPortfolioDataNode(ApplicationLoggingMixin):
    def __init__(self, llm: LlmAdapter):
        self._llm = llm

    def __call__(self, state: PortfolioInsightsState) -> dict:
        intent = state["portfolio_query"] if "portfolio_query" in state and state["portfolio_query"] is not None else PortfolioQueryIntent()
        results: list[str] = []

        exchange_tool = self._llm.get_tool("exchange_read_api")
        target_exchanges = [intent.exchange] if intent.exchange else ["CRYPTO_DOT_COM"]

        # 1. Fetch authoritative live exchange balances
        if exchange_tool is not None:
            for ex in target_exchanges:
                try:
                    live_balances = exchange_tool.invoke({
                        "operation": "get_balances",
                        "exchange": ex,
                    })
                    results.append(str(live_balances))
                except Exception as exc:  # pylint: disable=broad-except
                    self.app_logger.error(f"Error fetching live exchange balances for {ex}: {exc}")

                if intent.target_asset:
                    try:
                        ticker_data = exchange_tool.invoke({
                            "operation": "get_ticker",
                            "exchange": ex,
                            "ticker_symbol": intent.target_asset,
                        })
                        results.append(f"Exchange Ticker ({intent.target_asset}):\n{ticker_data}")
                    except Exception as exc:  # pylint: disable=broad-except
                        self.app_logger.error(f"Error fetching exchange ticker: {exc}")

        # 2. Fetch risk manager quote portfolio summary
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

        if not results:
            return {"portfolio_data": "Portfolio summary tool is not available."}

        return {"portfolio_data": "\n\n".join(results)}
