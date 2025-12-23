import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BacktestConfig(BaseSettings):
    backtest_initial_balance: Optional[float] = 10000.0
    backtest_tick_delay: Optional[float] = Field(default=0.0)
    application_config_filepath: Optional[str] = Field(default=None, alias="application-conf")
    environment_config_filepath: Optional[str] = Field(default=None)
    assets_config_filepath: Optional[str] = Field(alias="assets-conf")
    historical_data_path: Optional[str] = Field(default=os.path.join(
        os.path.abspath(os.getcwd()), "localstorage", "coinmarketcap", "history"
    ))

    model_config = SettingsConfigDict(cli_parse_args=True)
