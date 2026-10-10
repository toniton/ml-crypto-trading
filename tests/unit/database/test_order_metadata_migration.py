from unittest.mock import MagicMock, patch

from src.database.migrations.versions.m1a2b3c4d5e6_order_metadata_column import (
    downgrade,
    upgrade,
)


class TestOrderMetadataMigration:
    def test_upgrade_adds_metadata_column_when_orders_table_exists(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["orders"]
        mock_inspector.get_columns.return_value = [{"name": "id"}, {"name": "uuid"}]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.m1a2b3c4d5e6_order_metadata_column.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            upgrade()
            mock_op.add_column.assert_called_once()
            args, _ = mock_op.add_column.call_args
            assert args[0] == "orders"
            assert args[1].name == "metadata"

    def test_upgrade_skips_when_column_already_present(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["orders"]
        mock_inspector.get_columns.return_value = [{"name": "id"}, {"name": "metadata"}]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.m1a2b3c4d5e6_order_metadata_column.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            upgrade()
            mock_op.add_column.assert_not_called()

    def test_upgrade_skips_when_orders_table_does_not_exist(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = []

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.m1a2b3c4d5e6_order_metadata_column.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            upgrade()
            mock_op.add_column.assert_not_called()

    def test_downgrade_drops_metadata_column(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["orders"]
        mock_inspector.get_columns.return_value = [{"name": "metadata"}]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.m1a2b3c4d5e6_order_metadata_column.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            downgrade()
            mock_op.drop_column.assert_called_once_with("orders", "metadata")

    def test_downgrade_skips_when_column_missing(self):
        mock_bind = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = ["orders"]
        mock_inspector.get_columns.return_value = [{"name": "id"}]

        with patch("sqlalchemy.inspect", return_value=mock_inspector), \
             patch("src.database.migrations.versions.m1a2b3c4d5e6_order_metadata_column.op") as mock_op:
            mock_op.get_bind.return_value = mock_bind
            downgrade()
            mock_op.drop_column.assert_not_called()
