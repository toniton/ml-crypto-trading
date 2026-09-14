import unittest
from decimal import Decimal
from queue import Queue
from unittest.mock import MagicMock

from api.interfaces.account_balance import AccountBalance
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.trading_context import TradingContext
from src.trading.managers.manager_container import ManagerContainer
from src.trading.trading_executor import TradingExecutor


class TestTradingExecutorRetry(unittest.TestCase):
    def setUp(self):
        self.asset = MagicMock()
        self.asset.enabled = True
        self.asset.key = 42
        self.asset.ticker_symbol = "BTC_USD"
        self.asset.quote_ticker_symbol = "USD"
        self.asset.exchange.value = "BINANCE"
        self.asset.min_quantity = 0.001
        self.asset.quantity_decimals = 4

        self.account_manager = MagicMock()
        self.market_data_manager = MagicMock()
        self.session_manager = MagicMock()
        self.consensus_manager = MagicMock()
        self.fees_manager = MagicMock()
        self.order_manager = MagicMock()
        self.protection_manager = MagicMock()
        self.websocket_manager = MagicMock()

        container = MagicMock(spec=ManagerContainer)
        container.account_manager = self.account_manager
        container.market_data_manager = self.market_data_manager
        container.session_manager = self.session_manager
        container.consensus_manager = self.consensus_manager
        container.fees_manager = self.fees_manager
        container.order_manager = self.order_manager
        container.protection_manager = self.protection_manager
        container.websocket_manager = self.websocket_manager

        self.activity_queue = Queue()
        self.executor = TradingExecutor(
            assets=[self.asset],
            manager_container=container,
            activity_queue=self.activity_queue,
        )

    def test_create_buy_order_retries_and_succeeds_when_uninitialized(self):
        context = TradingContext(
            starting_balance=Decimal("1000.0"),
            ticker_symbol=self.asset.ticker_symbol,
            exchange=self.asset.exchange.value,
        )
        self.session_manager.get_trading_context.side_effect = [None, context, context]
        self.account_manager.init_asset_balance.return_value = True

        balance = AccountBalance(currency="USD", available_balance=Decimal("1000.0"))
        market_data = MarketData(
            volume=Decimal("10"),
            high_price=Decimal("51000"),
            low_price=Decimal("49000"),
            close_price=Decimal("50000"),
            timestamp=1700000000,
        )
        self.account_manager.get_quote_balance.return_value = balance
        self.market_data_manager.get_market_data.return_value = market_data
        self.market_data_manager.get_candles.return_value = []
        self.fees_manager.get_instrument_fees.return_value = Fees(Decimal("0.001"), Decimal("0.001"))
        self.protection_manager.can_trade.return_value = True
        self.consensus_manager.evaluate.return_value = MagicMock(quorum=False)

        self.executor.create_buy_order([self.asset])

        self.account_manager.init_asset_balance.assert_called_once_with(self.asset, self.session_manager)

    def test_create_buy_order_skips_when_retry_fails(self):
        self.session_manager.get_trading_context.return_value = None
        self.account_manager.init_asset_balance.return_value = False

        self.executor.create_buy_order([self.asset])

        self.account_manager.init_asset_balance.assert_called_once_with(self.asset, self.session_manager)
        self.market_data_manager.get_market_data.assert_not_called()

    def test_create_sell_order_retries_and_succeeds_when_uninitialized(self):
        context = TradingContext(
            starting_balance=Decimal("1000.0"),
            ticker_symbol=self.asset.ticker_symbol,
            exchange=self.asset.exchange.value,
        )
        self.session_manager.get_trading_context.side_effect = [None, context]
        self.account_manager.init_asset_balance.return_value = True

        self.executor.create_sell_order([self.asset])

        self.account_manager.init_asset_balance.assert_called_once_with(self.asset, self.session_manager)

    def test_create_sell_order_skips_when_retry_fails(self):
        self.session_manager.get_trading_context.return_value = None
        self.account_manager.init_asset_balance.return_value = False

        self.executor.create_sell_order([self.asset])

        self.account_manager.init_asset_balance.assert_called_once_with(self.asset, self.session_manager)
        self.market_data_manager.get_market_data.assert_not_called()
