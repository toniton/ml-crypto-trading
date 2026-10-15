from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.database.migrations.versions.p1a2b3c4d5e6_retention_tables import (
    downgrade,
    upgrade,
)

_MODULE = "src.database.migrations.versions.p1a2b3c4d5e6_retention_tables"


class TestRetentionMigration:
    def test_upgrade_creates_tables_when_missing(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["orders"]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch(f"{_MODULE}.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            upgrade()
            assert mock_op.create_table.call_count == 3
            assert mock_op.create_index.call_count == 8

    def test_upgrade_skips_when_tables_exist(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = [
            "retention_runs",
            "retention_audit_events",
            "retention_holds",
        ]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch(f"{_MODULE}.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            upgrade()
            mock_op.create_table.assert_not_called()

    def test_downgrade_drops_all_tables(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = [
            "retention_runs",
            "retention_audit_events",
            "retention_holds",
        ]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch(f"{_MODULE}.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            downgrade()
            assert mock_op.drop_table.call_count == 3
