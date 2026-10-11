from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.database.migrations.versions.n1a2b3c4d5e6_walk_forward_tables import (
    downgrade,
    upgrade,
)


class TestWalkForwardMigration:
    def test_upgrade_creates_table_when_missing(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["orders", "backtest_sessions"]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.n1a2b3c4d5e6_walk_forward_tables.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            upgrade()
            mock_op.create_table.assert_called_once()
            args, _ = mock_op.create_table.call_args
            assert args[0] == "walk_forward_runs"
            assert mock_op.create_index.call_count == 2

    def test_upgrade_skips_when_table_already_exists(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["walk_forward_runs"]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.n1a2b3c4d5e6_walk_forward_tables.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            upgrade()
            mock_op.create_table.assert_not_called()

    def test_downgrade_drops_table_when_exists(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["walk_forward_runs"]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.n1a2b3c4d5e6_walk_forward_tables.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            downgrade()
            mock_op.drop_table.assert_called_once_with("walk_forward_runs")
            assert mock_op.drop_index.call_count == 2
