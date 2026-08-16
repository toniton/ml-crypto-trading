from typing import List

from langchain_core.tools import BaseTool

from api.interfaces.asset import Asset
from src.core.interfaces.llm_adapter import LlmAdapter
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class TradingOracle(ApplicationLoggingMixin):
    def __init__(self, llm: LlmAdapter):
        self._llm = llm
        self._tools: List[BaseTool] = []

    def register_tool(self, tool: BaseTool):
        self._tools.append(tool)
        self._llm.bind_tools(self._tools)

    def register_tools(self, tools: List[BaseTool]):
        self._tools.extend(tools)
        self._llm.bind_tools(self._tools)

    def generate_report(self, assets: list[Asset]):
        prompt = (
            f"Generate a detailed trading report for focus assets: {[a.ticker_symbol for a in assets]}. "
            "You can use the 'get_trading_context', 'get_exchange_fees', "
            "'get_market_statistics', and 'get_open_orders' tools to fetch more details about each asset if needed. "
            "IMPORTANT: Call each tool separately for EACH individual asset. "
            "Pass a single string for ticker_symbol, not a list."
        )
        self.app_logger.info(f"Generating report for {[a.ticker_symbol for a in assets]}...")
        report = self._llm.generate(prompt)
        self.app_logger.info(f"Report generated:\n{report}")
        return report
