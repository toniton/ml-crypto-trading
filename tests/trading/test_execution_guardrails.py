# pylint: disable=protected-access,too-many-instance-attributes
from decimal import Decimal
from queue import Queue
from unittest import TestCase
from unittest.mock import MagicMock

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from src.events.message_event_bus import MessageEventBus
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.consensus.consensus_decision import ConsensusDecision
from src.trading.events import DecisionRejectedEvent, DecisionRejectedReason
from src.trading.managers.manager_container import ManagerContainer
from src.trading.trading_executor import TradingExecutor


class ExecutionGuardrailsTest(TestCase):
    def setUp(self):
        self.event_bus = MessageEventBus()
        self.events: list[DecisionRejectedEvent] = []
        self.event_bus.handler("DecisionRejectedEvent")(self.events.append)

        self.asset = Asset(
            base_ticker_symbol="BTC",
            quote_ticker_symbol="USD",
            quote_decimals=2,
            name="Bitcoin",
            exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
            min_quantity=0.01,
            quantity_decimals=4,
            schedule=AssetSchedule.EVERY_SECOND,
            candles_timeframe=Timeframe.MIN1,
        )

        self.mock_account_mgr = MagicMock()
        self.mock_market_mgr = MagicMock()
        self.mock_fees_mgr = MagicMock()
        self.mock_order_mgr = MagicMock()
        self.mock_session_mgr = MagicMock()
        self.mock_consensus_mgr = MagicMock()
        self.mock_protection_mgr = MagicMock()

        self.mock_protection_mgr.can_trade.return_value = True

        self.container = ManagerContainer(
            account_manager=self.mock_account_mgr,
            market_data_manager=self.mock_market_mgr,
            fees_manager=self.mock_fees_mgr,
            order_manager=self.mock_order_mgr,
            session_manager=self.mock_session_mgr,
            consensus_manager=self.mock_consensus_mgr,
            protection_manager=self.mock_protection_mgr,
            websocket_manager=MagicMock(),
            rest_manager=MagicMock(),
        )
        self.activity_queue = Queue()
        self.executor = TradingExecutor(
            assets=[self.asset],
            manager_container=self.container,
            activity_queue=self.activity_queue,
            event_bus=self.event_bus,
        )

    def test_calculate_quantity_falls_back_to_min_quantity(self):
        mock_parser = MagicMock()
        mock_parser.parse.return_value = Decimal("0.005")
        self.executor._dynamic_quantity_parser = mock_parser

        market_data = MarketData(
            low_price=Decimal("100"),
            high_price=Decimal("100"),
            close_price=Decimal("100"),
            volume=Decimal("1"),
            timestamp=100.0,
        )
        decision = ConsensusDecision(
            trade_action=TradeAction.BUY,
            ticker_symbol="BTC_USD",
            votes={"strategy_1": True},
            weights={"strategy_1": 1.0},
            factor=1.0,
        )

        result = self.executor._calculate_quantity(self.asset, TradeAction.BUY, market_data, decision)
        self.assertEqual(result, Decimal("0.01"))

    def test_calculate_quantity_accepts_above_min_quantity(self):
        mock_parser = MagicMock()
        mock_parser.parse.return_value = Decimal("0.05")
        self.executor._dynamic_quantity_parser = mock_parser

        market_data = MarketData(
            low_price=Decimal("100"),
            high_price=Decimal("100"),
            close_price=Decimal("100"),
            volume=Decimal("1"),
            timestamp=100.0,
        )
        decision = ConsensusDecision(
            trade_action=TradeAction.BUY,
            ticker_symbol="BTC_USD",
            votes={"strategy_1": True},
            weights={"strategy_1": 1.0},
            factor=1.0,
        )

        result = self.executor._calculate_quantity(self.asset, TradeAction.BUY, market_data, decision)
        self.assertEqual(result, Decimal("0.0500"))

    def test_validate_execution_edge_rejects_excessive_friction(self):
        market_data = MarketData(
            low_price=Decimal("100"),
            high_price=Decimal("100"),
            close_price=Decimal("100"),
            volume=Decimal("1"),
            timestamp=100.0,
        )
        abnormal_fees = Fees(maker_fee_pct=Decimal("6.0"), taker_fee_pct=Decimal("6.0"))
        valid = self.executor._validate_execution_edge(
            self.asset, TradeAction.BUY, market_data, abnormal_fees
        )
        self.assertFalse(valid)

        rejected = [e for e in self.events if e.reason == DecisionRejectedReason.NEGATIVE_EDGE.value]
        self.assertEqual(len(rejected), 1)

    def test_validate_execution_edge_accepts_normal_fees(self):
        market_data = MarketData(
            low_price=Decimal("100"),
            high_price=Decimal("100"),
            close_price=Decimal("100"),
            volume=Decimal("1"),
            timestamp=100.0,
        )
        normal_fees = Fees(maker_fee_pct=Decimal("0.1"), taker_fee_pct=Decimal("0.1"))
        valid = self.executor._validate_execution_edge(
            self.asset, TradeAction.BUY, market_data, normal_fees
        )
        self.assertTrue(valid)

    def test_create_buy_order_rejects_insufficient_balance(self):
        self.mock_order_mgr.has_outstanding_intent.return_value = False
        self.mock_account_mgr.get_quote_balance.return_value = AccountBalance(
            currency="USD",
            available_balance=Decimal("5.0"),
        )
        market_data = MarketData(
            low_price=Decimal("50000"),
            high_price=Decimal("50000"),
            close_price=Decimal("50000"),
            volume=Decimal("1"),
            timestamp=100.0,
        )
        self.mock_market_mgr.get_market_data.return_value = market_data
        self.mock_market_mgr.get_candles.return_value = []
        self.mock_fees_mgr.get_instrument_fees.return_value = Fees(
            maker_fee_pct=Decimal("0.1"), taker_fee_pct=Decimal("0.1")
        )
        self.mock_consensus_mgr.evaluate.return_value = ConsensusDecision(
            trade_action=TradeAction.BUY,
            ticker_symbol="BTC_USD",
            votes={"strategy_1": True},
            weights={"strategy_1": 1.0},
            factor=1.0,
        )

        self.executor.create_buy_order([self.asset])

        rejected = [e for e in self.events if e.reason == DecisionRejectedReason.INSUFFICIENT_BALANCE.value]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].symbol, "BTC_USD")
