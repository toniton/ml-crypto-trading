# pylint: disable=protected-access
from decimal import Decimal
from unittest.mock import MagicMock
import pytest

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.core.interfaces.database_manager import DatabaseManager
from src.core.interfaces.trading_journal import TradingJournal
from src.database.repositories.providers.postgres_order_repository import PostgresOrderRepository
from src.trading.orders.order_manager import OrderManager


def test_synchronous_execution_does_not_spawn_thread():
    mock_db = MagicMock(spec=DatabaseManager)
    mock_journal = MagicMock(spec=TradingJournal)
    mock_rest = MagicMock()
    mock_ws = MagicMock()
    mock_session = MagicMock()
    mock_bus = MagicMock()

    manager = OrderManager(
        database_manager=mock_db,
        trading_journal=mock_journal,
        rest_manager=mock_rest,
        websocket_manager=mock_ws,
        session_manager=mock_session,
        event_bus=mock_bus,
        synchronous_execution=True,
    )

    assert manager._execute_thread is None


def test_execute_order_marks_status_rejected_on_failure():
    mock_db = MagicMock(spec=DatabaseManager)
    mock_uow = MagicMock()
    mock_repo = MagicMock(spec=PostgresOrderRepository)
    mock_uow.get_repository.return_value = mock_repo
    mock_db.get_unit_of_work.return_value.__enter__.return_value = mock_uow

    mock_journal = MagicMock(spec=TradingJournal)
    mock_rest = MagicMock()
    mock_rest.place_order.side_effect = RuntimeError("INSUFFICIENT_AVAILABLE_BALANCE")
    mock_ws = MagicMock()
    mock_session = MagicMock()
    mock_bus = MagicMock()

    manager = OrderManager(
        database_manager=mock_db,
        trading_journal=mock_journal,
        rest_manager=mock_rest,
        websocket_manager=mock_ws,
        session_manager=mock_session,
        event_bus=mock_bus,
        synchronous_execution=True,
    )

    order = Order(
        uuid="test-uuid-fail",
        provider_name="CRYPTO_DOT_COM",
        ticker_symbol="CRO_USD",
        price=Decimal("0.059"),
        quantity="19",
        trade_action=TradeAction.SELL,
        created_time=1000.0,
        commit_hash="c8a56f7",
        status=OrderStatus.PENDING,
    )

    with pytest.raises(RuntimeError):
        manager.execute_order(order)

    assert order.status == OrderStatus.REJECTED
