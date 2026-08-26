from datetime import datetime, timezone
from unittest.mock import MagicMock

from api.interfaces.trade_action import OrderStatus, TradeAction
from src.database.dao.order_dao import OrderDao
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository

CREATED_AT = datetime(2026, 8, 22, 9, 14, 3, tzinfo=timezone.utc)


def build_dao(**overrides) -> OrderDao:
    defaults = dict(
        uuid="92121e15-0000-4000-8000-000000000001",
        provider_name="CRYPTO_DOT_COM",
        ticker_symbol="BTC_USD",
        price="63208.26661",
        quantity="0.00005",
        status=OrderStatus.PENDING.value,
        trade_action=TradeAction.BUY.value,
        last_updated_timestamp=CREATED_AT,
        created_timestamp=CREATED_AT,
        executed_timestamp=None,
    )
    defaults.update(overrides)
    return OrderDao(**defaults)


class TestGetNonTerminal:
    def test_returns_no_rows_when_empty(self):
        session = MagicMock()
        query = session.query.return_value
        filtered_query = query.filter.return_value
        filtered_query.all.return_value = []

        repo = PostgresOrderRepository(database_session=session)
        result = repo.get_non_terminal()

        session.query.assert_called_once_with(OrderDao)
        query.filter.assert_called_once()
        assert result == []

    def test_maps_rows_to_entities(self):
        session = MagicMock()
        query = session.query.return_value
        filtered_query = query.filter.return_value
        dao = build_dao(status=OrderStatus.PROCESSING.value)
        filtered_query.all.return_value = [dao]

        repo = PostgresOrderRepository(database_session=session)
        result = repo.get_non_terminal()

        assert len(result) == 1
        assert result[0].status is OrderStatus.PROCESSING
        assert result[0].uuid == dao.uuid
