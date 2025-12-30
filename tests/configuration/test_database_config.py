import unittest

import pytest
from unittest.mock import MagicMock, patch
from src.configuration.providers.database_config import DatabaseConfig
from src.configuration.environment_config import AppEnvEnum


class TestDatabaseConfig(unittest.TestCase):
    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        # Reset the singleton instance before each test
        DatabaseConfig._instance = None
        yield
        DatabaseConfig._instance = None

    def test_initialization_with_defaults(self):
        # Mock EnvironmentConfig and ApplicationConfig to avoid actual file reading
        with patch('src.configuration.providers.database_config.EnvironmentConfig') as MockEnvConfig:
            mock_env_instance = MockEnvConfig.return_value
            mock_env_instance.postgres_user = 'test_user'
            mock_env_instance.postgres_password.get_secret_value.return_value = 'test_pass'
            mock_env_instance.postgres_database = 'test_db'
            mock_env_instance.app_env = AppEnvEnum.STAGING
            mock_env_instance.database_connection_host = 'localhost:5432'

            config = DatabaseConfig()

            assert config.postgres_user == 'test_user'
            assert config.postgres_database == 'test_db'
            assert config.database_connection_host == 'localhost:5432'

            # Verify dependencies were instantiated
            MockEnvConfig.assert_called_once()

    def test_initialization_with_explicit_configs(self):
        mock_env_config = MagicMock()
        mock_env_config.postgres_user = 'explicit_user'
        mock_env_config.postgres_password.get_secret_value.return_value = 'explicit_pass'
        mock_env_config.postgres_database = 'explicit_db'
        mock_env_config.database_connection_host = 'explicit_host'

        config = DatabaseConfig(environment_config=mock_env_config)

        assert config.postgres_user == 'explicit_user'
        assert config.postgres_database == 'explicit_db'
        assert config.database_connection_host == 'explicit_host'

    def test_get_connection_endpoint(self):
        mock_env_config = MagicMock()
        mock_env_config.postgres_user = 'user'
        mock_env_config.postgres_password.get_secret_value.return_value = 'password'
        mock_env_config.postgres_database = 'db_name'
        mock_env_config.database_connection_host = 'localhost:5432'

        config = DatabaseConfig(environment_config=mock_env_config)

        expected_url = "postgresql://user:password@localhost:5432/db_name"
        assert config.get_connection_endpoint() == expected_url

    def test_singleton_behavior(self):
        with patch('src.configuration.providers.database_config.EnvironmentConfig'), \
                patch('src.configuration.providers.database_config.ApplicationConfig'):
            instance1 = DatabaseConfig.get_instance()
            instance2 = DatabaseConfig.get_instance()

            assert instance1 is instance2
