import sys
from unittest.mock import patch, MagicMock
import pytest
from testcontainers.postgres import PostgresContainer

from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.timeframe import Timeframe
from backtest.backtest_application import BacktestApplication
from src.configuration.application_config import ApplicationConfig
from src.configuration.assets_config import Asset
from src.configuration.environment_config import EnvironmentConfig
from src.core.interfaces.exchange_rest_client import ExchangeProvidersEnum

# pylint: disable=redefined-outer-name


@pytest.fixture(scope="module")
def postgres_container():
    try:
        with PostgresContainer("postgres:16") as postgres:
            yield postgres
    except Exception as e:
        pytest.skip(f"Failed to start Postgres container: {e}")


@pytest.fixture
def mock_data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()

    # Create mock CSV files for two assets (non-mini as per updated BacktestApplication)
    # Filenames should be snake_case to match ticker_symbol.lower() (BTC_USD -> btc_usd.csv)
    btc_content = """timestamp;open;high;low;close;volume;marketCap
2023-01-01 00:00:00;100;110;90;105;1000;1000000
2023-01-01 00:00:01;105;115;95;110;1100;1100000
"""
    (d / "btc_usd.csv").write_text(btc_content)

    eth_content = """timestamp;open;high;low;close;volume;marketCap
2023-01-01 00:00:00;10;11;9;10.5;100;100000
2023-01-01 00:00:01;10.5;11.5;9.5;11;110;110000
"""
    (d / "eth_usd.csv").write_text(eth_content)

    return str(d)


def test_backtest_run(postgres_container, mock_data_dir):
    with patch.object(sys, 'argv', ['app']):
        app_config = ApplicationConfig(**{
            "assets-conf": "dummy_conf.json",
            "backtest-mode": True
        })

    app_config.historical_data_path = mock_data_dir
    app_config.backtest_tick_delay = 0.01

    env_config = EnvironmentConfig(
        app_env="production",
        database_connection_host=f"{postgres_container.get_container_host_ip()}:"
                                 f"{postgres_container.get_exposed_port(5432)}",
        postgres_user=postgres_container.POSTGRES_USER,
        postgres_password=postgres_container.POSTGRES_PASSWORD,
        postgres_database=postgres_container.POSTGRES_DB
    )

    # Use Mock for AssetsConfig to avoid Pydantic validation complexity (expecting yaml files etc.)
    # inside the test environment. We just need it to hold the assets list.
    assets_config = MagicMock()
    assets_config.assets = [
        Asset(
            base_ticker_symbol="BTC",
            quote_ticker_symbol="USD",
            decimal_places=2,
            name="Bitcoin",
            exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
            min_quantity=0.0001,
            schedule=AssetSchedule.EVERY_MINUTE,
            candles_timeframe=Timeframe.MIN1
        ),
        Asset(
            base_ticker_symbol="ETH",
            quote_ticker_symbol="USD",
            decimal_places=2,
            name="Ethereum",
            exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
            min_quantity=0.01,
            schedule=AssetSchedule.EVERY_MINUTE,
            candles_timeframe=Timeframe.MIN1
        )
    ]

    # Run Backtest
    backtest_app = BacktestApplication(
        application_config=app_config,
        environment_config=env_config,
        assets_config=assets_config,
        is_backtest_mode=True
    )

    # Verify it runs without error
    try:
        backtest_app.startup()
    except Exception as e:
        pytest.fail(f"Backtest application failed to start/run: {e}")
