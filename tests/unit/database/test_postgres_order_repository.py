# pylint: disable=duplicate-code
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.database.dao.order_dao import OrderDao
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository

CREATED_AT = datetime(2026, 8, 22, 9, 14, 3, tzinfo=timezone.utc)


def build_dao(**overrides) -> OrderDao:
    defaults = {
        "uuid": "92121e15-0000-4000-8000-000000000001",
        "provider_name": "CRYPTO_DOT_COM",
        "ticker_symbol": "BTC_USD",
        "price": "63208.26661",
        "quantity": "0.00005",
        "status": OrderStatus.PENDING.value,
        "trade_action": TradeAction.BUY.value,
        "last_updated_timestamp": CREATED_AT,
        "created_timestamp": CREATED_AT,
        "executed_timestamp": None,
    }
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
        assert not result

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


class TestUpsert:
    def test_upsert_executes_statement_with_commit_hash(self):
        session = MagicMock()
        repo = PostgresOrderRepository(database_session=session)

        order = Order(
            uuid="test-uuid-123",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("63000.00"),
            quantity="0.05",
            trade_action=TradeAction.BUY,
            created_time=CREATED_AT.timestamp(),
            commit_hash="a" * 64,
            status=OrderStatus.PENDING,
        )

        repo.upsert(order)

        session.execute.assert_called_once()
        executed_clause = session.execute.call_args[0][0]
        compiled_params = executed_clause.compile().params
        assert compiled_params.get("commit_hash") == "a" * 64
        assert compiled_params.get("uuid") == "test-uuid-123"

    def test_upsert_executes_statement_with_order_commit_hash(self):
        session = MagicMock()
        repo = PostgresOrderRepository(database_session=session)

        order = Order(
            uuid="test-uuid-order-hash",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("63000.00"),
            quantity="0.05",
            trade_action=TradeAction.BUY,
            created_time=CREATED_AT.timestamp(),
            commit_hash="c4688f3b",
            status=OrderStatus.PENDING,
        )

        repo.upsert(order)

        session.execute.assert_called_once()
        executed_clause = session.execute.call_args[0][0]
        compiled_params = executed_clause.compile().params
        assert compiled_params.get("commit_hash") == "c4688f3b"
        assert compiled_params.get("uuid") == "test-uuid-order-hash"

    def test_upsert_executes_statement_with_attribution_fields(self):
        session = MagicMock()
        repo = PostgresOrderRepository(database_session=session)

        order = Order(
            uuid="test-uuid-attrib",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("63000.00"),
            quantity="0.05",
            trade_action=TradeAction.BUY,
            created_time=CREATED_AT.timestamp(),
            decision_id="dec-abc",
            winning_strategy="TrendA",
            strategy_votes={"TrendA": "BUY"},
            strategy_attributions={"TrendA": 1.0},
            status=OrderStatus.COMPLETED,
        )

        repo.upsert(order)

        session.execute.assert_called_once()
        executed_clause = session.execute.call_args[0][0]
        compiled_params = executed_clause.compile().params
        assert compiled_params.get("decision_id") == "dec-abc"
        assert compiled_params.get("metadata") == {
            "winning_strategy": "TrendA",
            "strategy_votes": {"TrendA": "BUY"},
            "strategy_attributions": {"TrendA": 1.0},
        }


class TestGetCompletedByExecutedRange:
    def test_queries_completed_orders_within_time_range(self):
        session = MagicMock()
        query = session.query.return_value
        filtered_query = query.filter.return_value
        ordered_query = filtered_query.order_by.return_value
        dao = build_dao(status=OrderStatus.COMPLETED.value, executed_timestamp=CREATED_AT)
        ordered_query.all.return_value = [dao]

        repo = PostgresOrderRepository(database_session=session)
        start = datetime(2026, 8, 22, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 8, 23, 0, 0, 0, tzinfo=timezone.utc)
        results = repo.get_completed_by_executed_range(start=start, end=end)

        session.query.assert_called_once_with(OrderDao)
        assert len(results) == 1
        assert results[0].status is OrderStatus.COMPLETED
        assert results[0].uuid == dao.uuid
