from unittest.mock import MagicMock, patch

import pytest
from src.configuration.environment_config import EnvironmentConfig


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

    with patch('src.core.logging.manager.EnvironmentConfig', return_value=mock_env), \
         patch('src.configuration.providers.database_config.EnvironmentConfig', return_value=mock_env):
        yield mock_env
