from __future__ import annotations

from typing import Type

import yaml
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from src.agent.configuration.configuration_service import ConfigurationService
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class ConfigurationInput(BaseModel):
    ticker_symbol: str = Field(
        description="A single ticker symbol of the asset (e.g., 'BTC_USD'). Do not pass a list."
    )


class ConfigurationTool(BaseTool, ApplicationLoggingMixin):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str = "get_configuration"
    description: str = (
        "Returns the current configuration for a SINGLE asset (schedule, consensus thresholds, "
        "strategies, guards, quantity limits)."
    )
    args_schema: Type[BaseModel] = ConfigurationInput
    configuration_service: ConfigurationService

    def __init__(self, configuration_service: ConfigurationService):
        super().__init__(configuration_service=configuration_service)

    def _run(self, ticker_symbol: str) -> str:  # pylint: disable=arguments-differ
        target = (ticker_symbol or "").strip()
        try:
            raw = self.configuration_service.load_raw_config()
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.error(f"Error loading configuration: {exc}")
            return f"Error loading configuration: {exc}"

        entry = self._find_asset_entry(raw, target)
        if entry is None:
            return f"Error: Asset {target} not found in configuration. Available: {available_symbols_from(raw)}"
        self.app_logger.info(f"Configuration for {target} requested by LLM.")
        return f"Configuration for {target}:\n" + yaml.safe_dump(entry, sort_keys=False)

    @staticmethod
    def _find_asset_entry(raw_config: dict, ticker_symbol: str) -> dict | None:
        for entry in raw_config.get("assets", []) or []:
            symbol = f"{entry.get('base_ticker_symbol')}_{entry.get('quote_ticker_symbol')}"
            if symbol == ticker_symbol:
                return entry
        return None


def available_symbols_from(raw_config: dict) -> list[str]:
    symbols = []
    for entry in raw_config.get("assets", []) or []:
        symbols.append(f"{entry.get('base_ticker_symbol')}_{entry.get('quote_ticker_symbol')}")
    return sorted(symbols)
