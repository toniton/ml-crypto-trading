# pylint: disable=duplicate-code
from decimal import Decimal
import unittest
from unittest.mock import MagicMock

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction, OrderStatus
from src.core.interfaces.trading_journal import TradingJournal
from src.core.interfaces.unit_of_work import UnitOfWork
from src.database.repositories.mappers.order_db_vs_entity_mapper import OrderDBVSEntityMapper
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.events.message_event_bus import MessageEventBus
from src.exchange.clients.cryptodotcom.cryptodotcom_rest_builder import CryptoDotComRestBuilder
from src.exchange.clients.cryptodotcom.cryptodotcom_rest_service import CryptoDotComRestService
from src.exchange.managers.rest_manager import RestManager
from src.trading.orders.order_manager import OrderManager
from src.trading.session.session_manager import SessionManager
from src.vcs.application.service import VCSService


class TestOrderAuditTrailTraceability(unittest.TestCase):
    def test_order_creation_pins_mandatory_commit_hash(self):
        order = Order(
            uuid="order-audit-1",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("63000.00"),
            quantity="0.05",
            trade_action=TradeAction.BUY,
            created_time=1700000000.0,
            commit_hash="56339b9",
            status=OrderStatus.PENDING,
        )

        self.assertEqual(order.commit_hash, "56339b9")
        self.assertIsInstance(order.commit_hash, str)

    def test_session_manager_provides_current_commit_hash(self):
        mock_vcs = MagicMock(spec=VCSService)
        head_commit = MagicMock()
        head_commit.hash = "56339b9"
        mock_vcs.head.return_value = head_commit

        session_manager = SessionManager(event_bus=MessageEventBus(), config_vcs=mock_vcs)
        session_manager.create_session("sess-1")

        self.assertEqual(session_manager.get_current_commit_hash(), "56339b9")

    def test_db_mapper_roundtrip_preserves_commit_hash(self):
        order = Order(
            uuid="order-audit-2",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("63000.00"),
            quantity="0.05",
            trade_action=TradeAction.BUY,
            created_time=1700000000.0,
            commit_hash="56339b9",
            status=OrderStatus.COMPLETED,
        )

        dao = OrderDBVSEntityMapper.map_to_db(order)
        self.assertEqual(dao.commit_hash, "56339b9")

        restored = OrderDBVSEntityMapper.map_to_entity(dao)
        self.assertEqual(restored.commit_hash, "56339b9")

    def test_execute_order_with_cryptodotcom_builder_preserves_commit_hash_without_type_error(self):
        rest_manager = RestManager()
        mock_crypto_service = MagicMock(spec=CryptoDotComRestService)
        mock_crypto_service.get_provider_name.return_value = "CRYPTO_DOT_COM"
        real_builder = CryptoDotComRestBuilder()
        mock_crypto_service.builder.return_value = real_builder
        rest_manager.register_service(mock_crypto_service)

        mock_db = MagicMock(spec=SqlAlchemyDatabaseManager)
        mock_uow = MagicMock(spec=UnitOfWork)
        mock_repo = MagicMock()
        mock_uow.get_repository.return_value = mock_repo
        mock_db.get_unit_of_work.return_value.__enter__.return_value = mock_uow

        manager = OrderManager(
            database_manager=mock_db,
            trading_journal=MagicMock(spec=TradingJournal),
            rest_manager=rest_manager,
            websocket_manager=MagicMock(),
            session_manager=MagicMock(),
            event_bus=MagicMock(),
            synchronous_execution=True,
        )

        order = Order(
            uuid="cb18b6d9-8fa6-46d2-b072-a781a574990e",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="CRO_USD",
            price=Decimal("0.058750"),
            quantity="19",
            trade_action=TradeAction.BUY,
            created_time=1791859557.583,
            commit_hash="f065cc98755278e106e0f5ea5e0064a39df2c7706645e04c2eb85744e47bd18a",
            status=OrderStatus.PENDING,
            winning_strategy="BreakoutBuy",
            strategy_votes={"HammerAccumulationStrategy": "TRUE", "BreakoutBuy": "TRUE"},
            strategy_attributions={"HammerAccumulationStrategy": 0.5, "BreakoutBuy": 0.5},
        )

        manager.execute_order(order)
        self.assertEqual(real_builder.get_params()["client_oid"], "cb18b6d9-8fa6-46d2-b072-a781a574990e")
