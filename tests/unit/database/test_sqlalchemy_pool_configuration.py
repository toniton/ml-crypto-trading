from unittest.mock import MagicMock, patch

from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager


def test_engine_receives_configured_pool_settings():
    with patch("src.database.sqlalchemy_database_manager.DatabaseConfig.get_instance") as mock_cfg_getter:
        mock_cfg = MagicMock()
        mock_cfg.get_connection_endpoint.return_value = "postgresql://user:pass@localhost:5432/db"
        mock_cfg.postgres_pool_size = 25
        mock_cfg.postgres_max_overflow = 35
        mock_cfg.postgres_pool_timeout = 45.0
        mock_cfg.postgres_pool_recycle = 1200
        mock_cfg_getter.return_value = mock_cfg

        with patch("src.database.sqlalchemy_database_manager.create_engine") as mock_create_engine:
            manager = SqlAlchemyDatabaseManager()
            manager.get_engine()

            mock_create_engine.assert_called_once_with(
                "postgresql://user:pass@localhost:5432/db",
                pool_size=25,
                max_overflow=35,
                pool_timeout=45.0,
                pool_recycle=1200,
                pool_pre_ping=True,
            )
