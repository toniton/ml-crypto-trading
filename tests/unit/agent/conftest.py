import pytest
import yaml

from src.configuration.trading_config import TradingConfig
from src.vcs.application.service import VCSService
from tests.unit.api_server.helpers import make_temp_db_manager

SAMPLE_CONFIG = """
assets:
  - name: "Bitcoin (Crypto.com)"
    base_ticker_symbol: "BTC"
    quote_ticker_symbol: "USD"
    exchange: "CRYPTO_DOT_COM"
    min_quantity: 0.00005
    quote_decimals: 2
    quantity_decimals: 5
    candles_timeframe: "MIN1"
    schedule: 1
    guard_config:
      max_drawdown_period: 8
      max_drawdown_percentage: 0.60
      cooldown_timeout: 5
    consensus:
      buy: 1.3
      sell: 0.5
dynamic_quantity: "max(min_qty, eq * 0.1)"
"""


@pytest.fixture
def sample_config(tmp_path):
    config_file = tmp_path / "trading-config.yaml"
    config_file.write_text(SAMPLE_CONFIG, encoding="utf-8")
    return str(config_file)


@pytest.fixture
def vcs():
    db_manager = make_temp_db_manager()
    vcs_service = VCSService(db_manager)
    vcs_service.seed_if_empty(
        TradingConfig.model_validate(yaml.safe_load(SAMPLE_CONFIG)),
        author="test",
        message="Initial test seed",
    )
    return vcs_service

