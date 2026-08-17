import pytest

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
