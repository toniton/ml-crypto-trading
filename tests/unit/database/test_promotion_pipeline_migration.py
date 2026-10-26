from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.database.migrations.versions.t1a2b3c4d5e6_promotion_pipeline_tables import (
    downgrade,
    upgrade,
)


class TestPromotionPipelineMigration:
    def test_upgrade_creates_tables_when_missing(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["experiments", "evidence_proposals"]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.t1a2b3c4d5e6_promotion_pipeline_tables.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            upgrade()
            assert mock_op.create_table.call_count == 4
            table_names = [call[0][0] for call in mock_op.create_table.call_args_list]
            assert "simulated_runs" in table_names
            assert "simulation_reports" in table_names
            assert "promotion_records" in table_names
            assert "promotion_audit_events" in table_names

    def test_upgrade_skips_when_tables_already_exist(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = [
            "simulated_runs",
            "simulation_reports",
            "promotion_records",
            "promotion_audit_events",
        ]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.t1a2b3c4d5e6_promotion_pipeline_tables.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            upgrade()
            mock_op.create_table.assert_not_called()

    def test_downgrade_drops_tables_when_exist(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = [
            "simulated_runs",
            "simulation_reports",
            "promotion_records",
            "promotion_audit_events",
        ]
        mock_inspector.get_indexes.return_value = []

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.t1a2b3c4d5e6_promotion_pipeline_tables.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            downgrade()
            assert mock_op.drop_table.call_count == 4
