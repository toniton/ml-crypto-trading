from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.database.migrations.versions.q1a2b3c4d5e6_walk_forward_execution_durability import (
    downgrade,
    upgrade,
)


class TestWalkForwardDurabilityMigration:
    def test_upgrade_adds_columns_and_indexes_when_table_exists(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["walk_forward_runs"]
        mock_inspector.get_columns.return_value = [
            {"name": "id"},
            {"name": "ticker_symbol"},
            {"name": "status"},
            {"name": "spec"},
            {"name": "summary"},
            {"name": "created_at"},
            {"name": "updated_at"},
        ]
        mock_inspector.get_indexes.return_value = []

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.q1a2b3c4d5e6_walk_forward_execution_durability.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            upgrade()

            assert mock_op.add_column.call_count == 6
            assert mock_op.create_index.call_count == 3

    def test_upgrade_skips_when_columns_already_exist(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["walk_forward_runs"]
        mock_inspector.get_columns.return_value = [
            {"name": "id"},
            {"name": "ticker_symbol"},
            {"name": "status"},
            {"name": "spec"},
            {"name": "summary"},
            {"name": "worker_id"},
            {"name": "started_at"},
            {"name": "completed_at"},
            {"name": "heartbeat_at"},
            {"name": "lease_expires_at"},
            {"name": "error_message"},
            {"name": "created_at"},
            {"name": "updated_at"},
        ]
        mock_inspector.get_indexes.return_value = [
            {"name": "ix_walk_forward_runs_status"},
            {"name": "ix_walk_forward_runs_lease_expires_at"},
            {"name": "ix_walk_forward_runs_heartbeat_at"},
        ]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.q1a2b3c4d5e6_walk_forward_execution_durability.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            upgrade()

            mock_op.add_column.assert_not_called()
            mock_op.create_index.assert_not_called()

    def test_downgrade_drops_indexes_and_columns(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["walk_forward_runs"]
        mock_inspector.get_indexes.return_value = [
            {"name": "ix_walk_forward_runs_status"},
            {"name": "ix_walk_forward_runs_lease_expires_at"},
            {"name": "ix_walk_forward_runs_heartbeat_at"},
        ]
        mock_inspector.get_columns.return_value = [
            {"name": "worker_id"},
            {"name": "started_at"},
            {"name": "completed_at"},
            {"name": "heartbeat_at"},
            {"name": "lease_expires_at"},
            {"name": "error_message"},
        ]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.q1a2b3c4d5e6_walk_forward_execution_durability.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            downgrade()

            assert mock_op.drop_index.call_count == 3
            assert mock_op.drop_column.call_count == 6
