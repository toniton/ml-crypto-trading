from __future__ import annotations

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplicationConfig(BaseSettings):
    backtest_mode: Optional[bool] = Field(default=False, alias="backtest-mode")
    backtest_initial_balance: Optional[float] = Field(default=10000.0)
    backtest_tick_delay: Optional[float] = Field(default=0.0)
    assets_config_filepath: Optional[str] = Field(alias="assets-conf")
    historical_data_path: Optional[str] = Field(default=os.path.join(
        os.path.abspath(os.getcwd()), "localstorage", "coinmarketcap", "history"
    ))

    model_config = SettingsConfigDict(cli_parse_args=True)
