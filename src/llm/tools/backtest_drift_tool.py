from __future__ import annotations

from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.backtest.analysis.drift_detector import BacktestDriftDetector, DriftReport
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class BacktestDriftInput(BaseModel):
    ticker_symbol: str = Field(
        description="Ticker symbol of the asset to check for drift (e.g., 'BTC_USD')."
    )


class BacktestDriftTool(BaseTool, ApplicationLoggingMixin):
    """LangChain tool that detects live vs backtest drift via a replay.

    Replays recorded live market data through the backtest engine and compares
    the simulated fills against actual live fills.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "detect_backtest_drift"
    description: str = (
        "Replay recently recorded live market data through the backtest and "
        "compare the simulated fills against the actual live fills to detect drift."
    )
    args_schema: Type[BaseModel] = BacktestDriftInput
    drift_detector: BacktestDriftDetector

    def __init__(self, drift_detector: BacktestDriftDetector):
        super().__init__(drift_detector=drift_detector)

    def _run(self, ticker_symbol: str) -> str:  # pylint: disable=arguments-differ
        report = self.drift_detector.detect(ticker_symbol)
        self.app_logger.info(f"Drift detection for {ticker_symbol}: drifted={report.drifted}")
        return self._format(report)

    @staticmethod
    def _format(report: DriftReport) -> str:
        return (
            f"Drift {report.ticker_symbol}:\n"
            f"  Simulated fills: {report.simulated_fill_count}\n"
            f"  Live fills: {report.live_fill_count}\n"
            f"  Fill count drift: {report.fill_count_drift}\n"
            f"  Quantity drift: {report.quantity_drift}\n"
            f"  Price drift: {report.price_drift}\n"
            f"  Drifted: {report.drifted}"
        )
