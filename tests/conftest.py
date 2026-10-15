import os
from unittest.mock import MagicMock, patch

from circuitbreaker import CircuitBreakerMonitor
import pytest

# Ensure required environment variables exist during pytest module collection
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_CONNECTION_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "password")
os.environ.setdefault("POSTGRES_DATABASE", "trading_bot")

# Ensure project root is on import path for tests
import sys, pathlib
_root = str(pathlib.Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from src.configuration.environment_config import EnvironmentConfig  # pylint: disable=wrong-import-position


@pytest.fixture(autouse=True, scope="session")
def setup_test_environment():
    mock_env = MagicMock(spec=EnvironmentConfig)
    mock_env.app_env = "production"
    mock_env.database_connection_host = "localhost"
    mock_env.log_dir = "."
    mock_env.log_level = "INFO"
    mock_env.postgres_user = "postgres"
    mock_env.postgres_database = "trading_bot"
    mock_env.postgres_password = MagicMock()
    mock_env.postgres_password.get_secret_value.return_value = "password"

    with patch('src.logging.manager.EnvironmentConfig', return_value=mock_env), \
         patch('src.configuration.providers.database_config.EnvironmentConfig', return_value=mock_env):
        yield mock_env


@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    for cb in CircuitBreakerMonitor.get_circuits():
        cb.reset()
    yield
    for cb in CircuitBreakerMonitor.get_circuits():
        cb.reset()
