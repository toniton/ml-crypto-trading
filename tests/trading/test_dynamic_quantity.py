import unittest
from decimal import Decimal
from queue import Queue
from unittest.mock import MagicMock

from api.interfaces.account_balance import AccountBalance
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.trading.consensus.consensus_decision import ConsensusDecision
from src.trading.managers.manager_container import ManagerContainer
from src.trading.trading_executor import TradingExecutor


def _decision(true=1, total=1, factor=1.3):
    votes = {f"s{i}": i < true for i in range(total)}
    weights = {f"s{i}": 1.0 for i in range(total)}
    return ConsensusDecision(TradeAction.BUY, "BTC_USD", votes, weights, factor)


class TestDynamicQuantity(unittest.TestCase):
    def _setup_executor(self, dynamic_quantity=None):
        assets = []
        manager_container = MagicMock(spec=ManagerContainer)
        activity_queue = Queue()

        self.account_manager = MagicMock()
        self.market_data_manager = MagicMock()
        self.session_manager = MagicMock()
        self.consensus_manager = MagicMock()
        self.fees_manager = MagicMock()
        self.order_manager = MagicMock()
        self.protection_manager = MagicMock()
        self.websocket_manager = MagicMock()

        manager_container.account_manager = self.account_manager
        manager_container.market_data_manager = self.market_data_manager
        manager_container.session_manager = self.session_manager
        manager_container.consensus_manager = self.consensus_manager
        manager_container.fees_manager = self.fees_manager
        manager_container.order_manager = self.order_manager
        manager_container.protection_manager = self.protection_manager
        manager_container.websocket_manager = self.websocket_manager

        executor = TradingExecutor(assets, manager_container, activity_queue, dynamic_quantity=dynamic_quantity)

        return executor, manager_container

    def _asset(self):
        asset = MagicMock()
        asset.min_quantity = 0.001
        asset.quantity_decimals = 3
        asset.exchange.value = "test_exchange"
        asset.ticker_symbol = "BTC_USD"
        asset.key = 1
        return asset

    def _market(self):
        return MarketData(
            volume=Decimal("100"),
            high_price=Decimal("110"),
            low_price=Decimal("90"),
            close_price=Decimal("100"),
            timestamp=123456789.0
        )

    def _stub_data_sources(self, position_qty=0, avg_entry=0):
        self.account_manager.get_quote_balance.return_value = AccountBalance("USD", Decimal("1000"))
        ctx = TradingContext("BTC_USD", "test_exchange", Decimal("1000"))
        ctx.position_qty = Decimal(position_qty)
        ctx.avg_entry_price = Decimal(avg_entry)
        self.session_manager.get_trading_context.return_value = ctx
        self.market_data_manager.get_candles.return_value = []

    def test_calculate_quantity_no_dynamic_quantity(self):
        executor, _ = self._setup_executor()

        self.assertEqual(
            executor._calculate_quantity(self._asset(), TradeAction.BUY, self._market(), _decision()),
            Decimal("0.001"),
        )

    def test_calculate_quantity_with_dynamic_quantity(self):
        executor, _ = self._setup_executor(dynamic_quantity="volume / 1000")
        self._stub_data_sources()

        # 100 / 1000 = 0.1
        self.assertEqual(
            executor._calculate_quantity(self._asset(), TradeAction.BUY, self._market(), _decision()),
            Decimal("0.1"),
        )

    def test_calculate_quantity_complex_expression(self):
        executor, _ = self._setup_executor(dynamic_quantity="avg(close, high, low) / 100")
        self._stub_data_sources()

        # avg(100, 110, 90) = 100
        self.assertEqual(
            executor._calculate_quantity(self._asset(), TradeAction.BUY, self._market(), _decision()),
            Decimal("1.0"),
        )

    def test_calculate_quantity_full_context(self):
        executor, _ = self._setup_executor(dynamic_quantity="balance + pnl + equity")
        self._stub_data_sources(position_qty=1, avg_entry=90)

        # balance(1000) + pnl(10) + equity(1100) = 2110
        self.assertEqual(
            executor._calculate_quantity(self._asset(), TradeAction.BUY, self._market(), _decision()),
            Decimal("2110.0"),
        )

    def test_calculate_quantity_with_error_rejects_trade(self):
        executor, _ = self._setup_executor(dynamic_quantity="unknown_var + 1")
        self._stub_data_sources()

        # Expression error -> reject (None), not fallback
        self.assertIsNone(
            executor._calculate_quantity(self._asset(), TradeAction.BUY, self._market(), _decision()),
        )

    def test_calculate_quantity_returns_none_falls_back(self):
        # Simulate parser returning None (e.g. empty expression)
        executor, _ = self._setup_executor(dynamic_quantity="volume / 1000")
        self._stub_data_sources()
        executor._dynamic_quantity_parser.parse = MagicMock(return_value=None)  # type: ignore[attr-defined]

        self.assertEqual(
            executor._calculate_quantity(self._asset(), TradeAction.BUY, self._market(), _decision()),
            Decimal("0.001"),
        )

    def test_calculate_quantity_with_conditionals(self):
        executor, _ = self._setup_executor(dynamic_quantity="(1.5 if confidence > 0.5 else 1.0) * volume / 100")
        self._stub_data_sources()

        # Test Case 1: confidence > 0.5 (vote ratio 4/5 = 0.8) -> 1.5
        quantity = executor._calculate_quantity(
            self._asset(), TradeAction.BUY, self._market(), _decision(true=4, total=5)
        )
        self.assertEqual(quantity, Decimal("1.5"))

        # Test Case 2: confidence <= 0.5 (vote ratio 3/10 = 0.3) -> 1.0
        quantity = executor._calculate_quantity(
            self._asset(), TradeAction.BUY, self._market(), _decision(true=3, total=10)
        )
        self.assertEqual(quantity, Decimal("1.0"))

    def test_signal_is_directional(self):
        executor, _ = self._setup_executor(dynamic_quantity="signal * volume / 100")
        self._stub_data_sources()

        # BUY -> signal = +1 -> 100/100 = 1.0
        buy_decision = ConsensusDecision(TradeAction.BUY, "BTC_USD", {"a": True}, {"a": 1.0}, 1.3)
        self.assertEqual(
            executor._calculate_quantity(self._asset(), TradeAction.BUY, self._market(), buy_decision),
            Decimal("1.0"),
        )
        # SELL -> signal = -1 -> -1.0 -> clamped to min_qty 0.001
        sell_decision = ConsensusDecision(TradeAction.SELL, "BTC_USD", {"a": True}, {"a": 1.0}, 0.5)
        self.assertEqual(
            executor._calculate_quantity(self._asset(), TradeAction.SELL, self._market(), sell_decision),
            Decimal("0.001"),
        )