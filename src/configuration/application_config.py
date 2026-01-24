from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplicationConfig(BaseSettings):
    backtest_mode: bool = Field(default=False, alias="backtest-mode")
    backtest_initial_balance: Decimal = Field(default=Decimal("10000.0"))
    backtest_tick_delay: float = Field(default=0.0)
    assets_config_filepath: str = Field(alias="assets-conf")
    historical_data_dir_path: Optional[str] = Field(default=None, alias="backtest-source")
    simulated: bool = Field(default=False, alias="simulated")

    model_config = SettingsConfigDict(
        cli_parse_args=True,
        populate_by_name=True,
        extra='ignore'
    )

    @model_validator(mode='after')
    def validate_modes(self) -> ApplicationConfig:
        if self.simulated and self.backtest_mode:
            raise ValueError('Cannot enable both simulated and backtest-mode at the same time')

        if self.backtest_mode and not self.historical_data_dir_path:
            raise ValueError('backtest-source is required when backtest-mode is enabled')

        if self.simulated:
            # Ignore backtest related fields if simulated is enabled
            self.backtest_mode = False
            self.historical_data_dir_path = None
            self.backtest_tick_delay = 0.0

        return self
