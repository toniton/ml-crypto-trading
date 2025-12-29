from __future__ import annotations


from typing import Optional
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplicationConfig(BaseSettings):
    backtest_mode: Optional[bool] = Field(default=False, alias="backtest-mode")
    backtest_initial_balance: Optional[float] = Field(default=10000.0)
    backtest_tick_delay: Optional[float] = Field(default=0.0)
    assets_config_filepath: Optional[str] = Field(alias="assets-conf")
    historical_data_dir_path: Optional[str] = Field(default=None, alias="backtest-source")

    model_config = SettingsConfigDict(cli_parse_args=True)

    @model_validator(mode='after')
    def check_backtest_source(self) -> ApplicationConfig:
        if self.backtest_mode and not self.historical_data_dir_path:
            raise ValueError('backtest-source is required when backtest-mode is enabled')
        return self
