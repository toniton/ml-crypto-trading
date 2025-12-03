from __future__ import annotations

import json
import logging
import threading
import time
from queue import Queue

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.trading.accounts.account_manager import AccountManager
from src.trading.consensus.consensus_manager import ConsensusManager
from src.trading.context.trading_context_manager import TradingContextManager
from src.trading.fees.fees_manager import FeesManager
from src.trading.helpers.portfolio_helper import PortfolioHelper
from src.trading.markets.market_data_manager import MarketDataManager
from src.trading.orders.order_helper import OrderHelper
from src.trading.orders.order_manager import OrderManager
from src.trading.protection.protection_manager import ProtectionManager
from src.trading.trading_scheduler import TradingScheduler


class TradingEngine:
    def __init__(
            self,
            trading_scheduler: TradingScheduler,
            assets: list[Asset],
            account_manager: AccountManager,
            fees_manager: FeesManager,
            order_manager: OrderManager,
            market_data_manager: MarketDataManager,
            consensus_manager: ConsensusManager,
            trading_context_manager: TradingContextManager,
            protection_manager: ProtectionManager,
            activity_queue: Queue
    ):
        self.trading_scheduler = trading_scheduler
        self.assets = assets
        self.account_manager = account_manager
        self.fees_manager = fees_manager
        self.order_manager = order_manager
        self.market_data_manager = market_data_manager
        self.consensus_manager = consensus_manager
        self.trading_context_manager = trading_context_manager
        self.order_queue = Queue()
        self.activity_queue = activity_queue
        self.protection_manager = protection_manager

    def init_application(self):
        self.account_manager.init_websocket()
        self.account_manager.init_account_balances(self.trading_context_manager)
        self.fees_manager.init_account_fees()

        self.trading_scheduler.start(self.create_new_order)
        self.trading_scheduler.start(self.check_unclosed_orders)

        execute_thread = threading.Thread(target=self.execute_queued_orders, args=(self.activity_queue,), daemon=False)
        market_data_thread = threading.Thread(target=self.market_data_manager.init_websocket, daemon=False)
        execute_thread.start()
        market_data_thread.start()

    def execute_queued_orders(self, activity_queue: Queue):
        while True:
            msg = self.order_queue.get()
            activity_queue.put_nowait(msg)

            record = json.loads(msg)
            order = Order(**record)

            try:
                self.order_manager.execute_order(order)
            except Exception as exc:
                logging.error([f"Executing order failed. Order={order} . ->", exc])
            print(["msg", msg])

    def _fetch_market_data(self, asset: Asset) -> MarketData:
        market_data = self.market_data_manager.get_latest_marketdata(asset.key)
        return market_data or self.order_manager.get_market_data(asset.ticker_symbol, asset.exchange.value)

    def _should_trade(self, asset: Asset, action: TradeAction, market_data: MarketData, candles: list[Candle]) -> bool:
        trading_context = self.trading_context_manager.get_trading_context(asset.key)

        if not self.protection_manager.can_trade(asset.key, action, trading_context):
            return False

        consensus_result = self.consensus_manager.get_quorum(
            action, asset.ticker_symbol, trading_context, market_data, candles
        )
        logging.warning([
            f"Consensus={consensus_result} for asset={asset}"
        ])
        return bool(consensus_result)

    def _prepare_trade_context(self, asset: Asset) -> tuple[AccountBalance, MarketData, list[Candle], Fees]:
        account_balance = self.account_manager.get_balance(asset.ticker_symbol, asset.exchange.value)
        if account_balance.available_balance <= 0:
            raise ValueError(f"Insufficient balance for {asset.ticker_symbol}: ${account_balance.available_balance}")

        market_data = self._fetch_market_data(asset)
        fees = self.fees_manager.get_instrument_fees(asset.ticker_symbol, asset.exchange.value)
        candles = self.order_manager.get_candles(asset.exchange.value, asset.ticker_symbol, asset.candles_timeframe)

        return account_balance, market_data, candles, fees

    def create_new_order(self, assets: list[Asset]):
        for asset in assets:
            try:
                account_balance, market_data, candles, fees = self._prepare_trade_context(asset)

                if not self._should_trade(asset, TradeAction.BUY, market_data, candles):
                    logging.info(f"No consensus to buy {asset.ticker_symbol}")
                    continue

                price = market_data.close_price
                price = float(price) + (float(price) * fees.maker_fee_pct * 0.01)
                price = format(round(price, asset.decimal_places), f".{asset.decimal_places}f")

                logging.warning([
                    f"Fetched price for Asset. Asset={asset} Price={price}",
                    f"Fees={fees}",
                    f"Available balance={account_balance.available_balance}"
                ])
                quantity = format(asset.min_quantity, "f")
                order = self.order_manager.open_order(
                    ticker_symbol=asset.ticker_symbol,
                    quantity=quantity,
                    price=str(price),
                    provider_name=asset.exchange.value
                )
                self.order_queue.put(order.model_dump_json())
                self.trading_context_manager.record_buy(asset.key, order)
            except Exception as exc:
                logging.error([f"Error occurred processing asset. Asset={asset}", exc])

    def check_unclosed_orders(self, assets: list[Asset]):
        for asset in assets:
            try:
                trading_context = self.trading_context_manager.get_trading_context(asset.key)
                if not trading_context.open_positions:
                    logging.info([f"No open positions for asset. Asset={asset}"])
                    continue
                _, market_data, candles, fees = self._prepare_trade_context(asset)
                current_price = market_data.close_price

                logging.warning([f"Fetched current_price for {asset}. Price={current_price}", f"Fees={fees}"])

                if not self._should_trade(asset, TradeAction.SELL, market_data, candles):
                    continue

                open_orders: list[Order] = sorted(
                    filter(OrderHelper.less_than_price_filter(current_price), trading_context.open_positions),
                    key=lambda o, _current_price=market_data.close_price: (
                            (float(_current_price) - float(o.price)) / float(o.price)
                    )
                )

                best_order: Order | None = next(iter(open_orders), None)
                if best_order:
                    closed_order = self.order_manager.close_order(best_order, current_price)
                    self.order_queue.put(closed_order.model_dump_json())
                    self.trading_context_manager.record_sell(asset.key, closed_order)

            except Exception as exc:
                logging.error([f"Error occurred finalizing asset. Asset={asset}", exc])
        logging.info(["Threading..., sleeping...."])

    def backfill_trading_context(self):
        # Check DB for unclosed orders and add it to trading context
        # closing_orders = self.order_manager.get_closing_orders(asset.ticker_symbol, price)
        ...

    def print_context(self) -> None:
        for asset in self.assets:
            try:
                trading_context = self.trading_context_manager.get_trading_context(asset.key)
                trading_context.end_time = time.time()
                market_data = self.market_data_manager.get_latest_marketdata(asset.key)
                if market_data is None:
                    market_data = self.order_manager.get_market_data(asset.ticker_symbol, asset.exchange.value)

                print("Trading Context")
                print(f"======= {asset.ticker_symbol} =======================")
                print(["Portfolio value", PortfolioHelper.calculate_portfolio_value(trading_context.available_balance,
                                                                                    market_data.close_price,
                                                                                    trading_context.open_positions)
                       ])
                print(["Unrealized PNL value", PortfolioHelper.calculate_unrealized_pnl_value(
                    trading_context.starting_balance, market_data.close_price,
                    trading_context.open_positions, trading_context.close_positions
                )
                       ])
                print(["self.start_time", trading_context.start_time])
                print(["self.starting_balance", trading_context.starting_balance])
                print(["self.available_balance", trading_context.available_balance])
                print(["self.closing_balance", trading_context.closing_balance])
                print(["self.buy_count", trading_context.buy_count])
                print(["self.lowest_buy", trading_context.lowest_buy])
                print(["self.highest_buy", trading_context.highest_buy])
                print(["self.lowest_sell", trading_context.lowest_sell])
                print(["self.highest_sell", trading_context.highest_sell])
                print(["self.open_positions", trading_context.open_positions])
                print(["self.close_positions", trading_context.close_positions])
                print(["self.end_time", trading_context.end_time])
                print(["self.last_activity_time", trading_context.last_activity_time])
            except Exception as exc:
                print(exc)
