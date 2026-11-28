from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.database.migrations.versions.o1a2b3c4d5e6_experiments_table import (
    downgrade,
    upgrade,
)


class TestExperimentMigration:
    def test_upgrade_creates_table_when_missing(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["orders", "walk_forward_runs"]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.o1a2b3c4d5e6_experiments_table.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            upgrade()
            mock_op.create_table.assert_called_once()
            args, _ = mock_op.create_table.call_args
            assert args[0] == "experiments"
            assert mock_op.create_index.call_count == 4

    def test_upgrade_skips_when_table_already_exists(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["experiments"]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.o1a2b3c4d5e6_experiments_table.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            upgrade()
            mock_op.create_table.assert_not_called()

    def test_downgrade_drops_table_when_exists(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["experiments"]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.o1a2b3c4d5e6_experiments_table.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            downgrade()
            mock_op.drop_table.assert_called_once_with("experiments")
            assert mock_op.drop_index.call_count == 4


class TestExperimentRunHistoryMigration:
    def test_upgrade_adds_run_history_column_when_missing(self):
        from src.database.migrations.versions.x1a2b3c4d5e6_experiment_run_history import (
            upgrade as history_upgrade,
        )

        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["experiments"]
        mock_inspector.get_columns.return_value = [{"name": "id"}, {"name": "report"}]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.x1a2b3c4d5e6_experiment_run_history.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            history_upgrade()
            mock_op.add_column.assert_called_once()
            assert mock_op.add_column.call_args[0][0] == "experiments"

    def test_downgrade_drops_run_history_column_when_present(self):
        from src.database.migrations.versions.x1a2b3c4d5e6_experiment_run_history import (
            downgrade as history_downgrade,
        )

        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["experiments"]
        mock_inspector.get_columns.return_value = [{"name": "id"}, {"name": "run_history"}]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.x1a2b3c4d5e6_experiment_run_history.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            history_downgrade()
            mock_op.drop_column.assert_called_once_with("experiments", "run_history")
