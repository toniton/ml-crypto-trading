import json
import logging
import threading
import time
from queue import Queue

from schedule import run_pending, every

from api.interfaces.asset import Asset
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


class TradingEngine:
    assets: list[Asset]
    account_manager: AccountManager
    order_manager: OrderManager
    market_data_manager: MarketDataManager
    consensus_manager: ConsensusManager
    trading_context_manager: TradingContextManager
    protection_manager: ProtectionManager

    def __init__(
            self,
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

    @staticmethod
    def run_threaded_schedule(job_func):
        job_thread = threading.Thread(target=job_func)
        job_thread.start()

    def init_application(self):
        self.account_manager.init_account_balances(self.trading_context_manager)
        self.fees_manager.init_account_fees()
        try:
            every().second.do(TradingEngine.run_threaded_schedule, self.create_new_order)
            every().second.do(TradingEngine.run_threaded_schedule, self.check_unclosed_orders)
        except Exception as exc:
            logging.error(["Error occurred initializing application. ->", exc])

        schedule_thread = threading.Thread(target=self.run_pending_schedules)
        execute_thread = threading.Thread(target=self.execute_queued_orders, args=(self.activity_queue,))
        market_data_thread = threading.Thread(target=self.market_data_checker)
        schedule_thread.start()
        execute_thread.start()
        market_data_thread.start()

    @staticmethod
    def run_pending_schedules():
        while True:
            run_pending()
            time.sleep(1)

    def execute_queued_orders(self, activity_queue: Queue):
        while True:
            msg = self.order_queue.get()
            activity_queue.put_nowait(msg)

            record = json.loads(msg)
            order = Order(**record)

            try:
                self.order_manager.execute_order(order)
            except Exception as exc:
                logging.error([f"Executing order {order.uuid} for {order.ticker_symbol} failed. ->", exc, order])
            print(["msg", msg])

    def create_new_order(self):
        for asset in self.assets:
            try:
                account_balance = self.account_manager.get_balance(asset.ticker_symbol, asset.exchange.value)
                fees = self.fees_manager.get_instrument_fees(asset.ticker_symbol, asset.exchange.value)
                if account_balance.available_balance <= 0:
                    raise ValueError(
                        f"Account balance too low to trade: ${account_balance.available_balance}. "
                        f"Position balance: ${account_balance.position_balance}"
                    )
                market_data = self.market_data_manager.get_latest_marketdata(asset.key)
                if market_data is None:
                    market_data = self.order_manager.get_market_data(asset.ticker_symbol, asset.exchange.value)

                price = market_data.close_price

                logging.warning([
                    f"Fetched price for ${asset.name} with ticker: ${asset.ticker_symbol} -> at {asset.exchange.value}",
                    price,
                    f"Fees: ${fees}",
                    f"Available balance: ${account_balance.available_balance}"
                ])

                trading_context = self.trading_context_manager.get_trading_context(asset.key)

                if self.protection_manager.can_trade(asset.key, TradeAction.BUY, trading_context):
                    candles = self.order_manager.get_candles(
                        asset.exchange.value,
                        asset.ticker_symbol,
                        asset.candles_timeframe
                    )

                    consensus_result = self.consensus_manager.get_quorum(
                        TradeAction.BUY, asset.ticker_symbol,
                        trading_context, market_data,
                        candles
                    )

                    if consensus_result:
                        price = float(price) + (float(price) * 0.0005)
                        price = format(round(price, asset.decimal_places), f".{asset.decimal_places}f")
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
                logging.error([
                    f"Error occurred processing asset ${asset.name} with ticker: ${asset.ticker_symbol} -> at {asset.exchange.value}",
                    exc
                ])

    def market_data_checker(self):
        self.market_data_manager.init_websocket()

    def check_unclosed_orders(self):
        for asset in self.assets:
            try:
                trading_context = self.trading_context_manager.get_trading_context(asset.key)
                # if len(trading_context.close_positions) == 3:
                #     # exit(1)
                #     raise RuntimeError(f"Hit max close positions for {asset.ticker_symbol}, manual review needed.")

                if not trading_context.open_positions:
                    logging.warning([
                        f"No open positions for asset ${asset.name} with ticker: ${asset.ticker_symbol} -> at {asset.exchange.value}"
                    ])
                    return

                market_data = self.market_data_manager.get_latest_marketdata(asset.key)
                if market_data is None:
                    market_data = self.order_manager.get_market_data(asset.ticker_symbol, asset.exchange.value)

                price = market_data.close_price
                fees = self.fees_manager.get_instrument_fees(asset.ticker_symbol, asset.exchange.value)

                logging.warning([
                    f"Fetched price for ${asset.name} with ticker: ${asset.ticker_symbol} -> at {asset.exchange.value}",
                    price,
                    f"Fees: ${fees}"
                ])

                candles = self.order_manager.get_candles(
                    asset.exchange.value,
                    asset.ticker_symbol,
                    asset.candles_timeframe
                )

                if self.protection_manager.can_trade(asset.key, TradeAction.SELL, trading_context):
                    consensus_result = self.consensus_manager.get_quorum(
                        TradeAction.SELL, asset.ticker_symbol,
                        trading_context, market_data,
                        candles
                    )

                    if not consensus_result:
                        logging.warning([
                            f"Could not reach consensus for asset ${asset.name} with ticker: ${asset.ticker_symbol} -> at {asset.exchange.value}"
                        ])
                        return

                    # TODO: Prioritize selling at a profit or least break even.
                    open_orders = filter(
                        OrderHelper.less_than_price_filter(price), trading_context.open_positions
                    )

                    # TODO: Remove this after testing.
                    open_orders = trading_context.open_positions

                    # TODO: Trigger only one sell at a time based on priority.
                    # TODO: Check quantity and loss for better risk management. Use protection rule for this.
                    for open_order in list(open_orders):
                        closed_order = self.order_manager.close_order(open_order, price)
                        self.order_queue.put(closed_order.model_dump_json())
                        self.trading_context_manager.record_sell(asset.key, closed_order)

            except Exception as exc:
                logging.error([
                    f"Error occurred finalizing asset ${asset.name} with ticker: ${asset.ticker_symbol} -> at {asset.exchange.value}",
                    exc
                ])
        print(["Threading..., sleeping...."])

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
