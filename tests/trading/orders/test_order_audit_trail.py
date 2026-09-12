from decimal import Decimal
import unittest
from unittest.mock import MagicMock

from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction, OrderStatus
from src.database.repositories.mappers.order_db_vs_entity_mapper import OrderDBVSEntityMapper
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

        session_manager = SessionManager(config_vcs=mock_vcs)
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
