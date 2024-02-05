import json
import logging
import threading
import time

import schedule
from kafka import KafkaProducer, KafkaConsumer

from entities.asset import Asset
from entities.order import Order
from entities.trade_action import TradeAction
from trading.consensus.consensus_manager import ConsensusManager
from trading.context.trading_context_manager import TradingContextManager
from trading.markets.market_data_manager import MarketDataManager
from trading.orders.order_helper import OrderHelper
from trading.orders.order_manager import OrderManager


class TradingEngine:
    assets: list[Asset]
    consumer: KafkaConsumer
    order_manager: OrderManager
    market_data_manager: MarketDataManager
    consensus_manager: ConsensusManager
    trading_context_manager: TradingContextManager

    def __init__(
        self,
        assets: list[Asset],
        consumer: KafkaConsumer,
        producer: KafkaProducer,
        order_manager: OrderManager,
        market_data_manager: MarketDataManager,
        consensus_manager: ConsensusManager,
        trading_context_manager: TradingContextManager
    ):
        self.assets = assets
        self.order_manager = order_manager
        self.market_data_manager = market_data_manager
        self.consensus_manager = consensus_manager
        self.trading_context_manager = trading_context_manager
        self.consumer = consumer
        self.producer = producer

    @staticmethod
    def run_threaded_schedule(job_func):
        job_thread = threading.Thread(target=job_func)
        job_thread.start()

    def init_application(self):
        try:
            self.consumer.subscribe([OrderManager.KAFKA_TOPIC])
            schedule.every().second.do(TradingEngine.run_threaded_schedule, self.create_new_order)
            schedule.every().second.do(TradingEngine.run_threaded_schedule, self.check_unclosed_orders)
        except Exception as exc:
            logging.error(["Error occurred initializing application. ->", exc])

        schedule_thread = threading.Thread(target=self.run_pending_schedules)
        execute_thread = threading.Thread(target=self.execute_queued_orders)
        market_data_thread = threading.Thread(target=self.market_data_checker)
        schedule_thread.start()
        execute_thread.start()
        market_data_thread.start()

    @staticmethod
    def run_pending_schedules():
        while True:
            schedule.run_pending()
            time.sleep(1)

    def execute_queued_orders(self):
        records = self.consumer.poll(timeout_ms=500)
        for msg in self.consumer:
            record = json.loads(msg.value.decode('utf-8'))
            order = Order(**record)
            try:
                self.order_manager.execute_order(order)
            except Exception as exc:
                logging.error([f"Executing order {order.uuid} for {order.ticker_symbol} failed. ->", exc, order])
            print(["msg", msg])
        print(["records", records])

    def create_new_order(self):
        for asset in self.assets:
            try:
                market_data = self.market_data_manager.get_latest_marketdata(asset)
                if market_data is None:
                    market_data = self.order_manager.get_market_data(asset.ticker_symbol, asset.exchange.value)

                price = market_data.close_price

                logging.warning([
                    f"Fetched price for ${asset.name} with ticker: ${asset.ticker_symbol} -> at {asset.exchange.value}",
                    price
                ])

                trading_context = self.trading_context_manager.get_trading_context(asset.ticker_symbol)

                consensus_result = self.consensus_manager.get_quorum(
                    TradeAction.BUY, asset.ticker_symbol,
                    trading_context, market_data
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

                    self.producer.send(OrderManager.KAFKA_TOPIC, order.model_dump_json())
                    trading_context.record_buy(order)
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
                trading_context = self.trading_context_manager.get_trading_context(asset.ticker_symbol)
                if not trading_context.open_positions:
                    logging.warning([
                        f"No open positions for asset ${asset.name} with ticker: ${asset.ticker_symbol} -> at {asset.exchange.value}"
                    ])
                    return

                market_data = self.market_data_manager.get_latest_marketdata(asset)
                if market_data is None:
                    market_data = self.order_manager.get_market_data(asset.ticker_symbol, asset.exchange.value)

                price = market_data.close_price

                logging.warning([
                    f"Fetched price for ${asset.name} with ticker: ${asset.ticker_symbol} -> at {asset.exchange.value}",
                    price
                ])

                consensus_result = self.consensus_manager.get_quorum(
                    TradeAction.SELL, asset.ticker_symbol,
                    trading_context, market_data
                )

                if not consensus_result:
                    logging.warning([
                        f"Could not reach consensus for asset ${asset.name} with ticker: ${asset.ticker_symbol} -> at {asset.exchange.value}"
                    ])
                    return

                closing_orders = filter(
                    OrderHelper.less_than_price_filter(price), trading_context.open_positions
                )

                quantity = 0
                for order in closing_orders:
                    quantity += float(order.quantity)
                    trading_context.open_positions.remove(order)

                order = self.order_manager.close_order(
                    ticker_symbol=asset.ticker_symbol,
                    quantity=str(quantity),
                    price=str(price),
                    provider_name=asset.exchange.value
                )

                self.producer.send(OrderManager.KAFKA_TOPIC, order.model_dump_json())
                trading_context.record_sell(order)
            except Exception as exc:
                logging.error([
                    f"Error occurred finalizing asset ${asset.name} with ticker: ${asset.ticker_symbol} -> at {asset.exchange.value}",
                    exc
                ])
        print(["Threading..., sleeping...."])
        pass

    def backfill_trading_context(self):
        # Check DB for unclosed orders and add it to trading context
        closing_orders = self.order_manager.get_closing_orders(asset.ticker_symbol, price)
        ...