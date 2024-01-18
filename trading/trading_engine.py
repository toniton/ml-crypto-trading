import json
import logging
import threading
import time

import schedule
from kafka import KafkaProducer, KafkaConsumer

from entities.asset import Asset
from entities.order import Order
from prediction.prediction_engine import PredictionEngine
from trading.markets.market_data_manager import MarketDataManager
from trading.orders.order_manager import OrderManager


class TradingEngine:
    assets: list[Asset]
    consumer: KafkaConsumer
    order_manager: OrderManager
    market_data_manager: MarketDataManager
    prediction_engine: PredictionEngine

    def __init__(
        self,
        assets: list[Asset],
        consumer: KafkaConsumer,
        producer: KafkaProducer,
        order_manager: OrderManager,
        market_data_manager: MarketDataManager,
        prediction_engine: PredictionEngine
    ):
        self.assets = assets
        self.order_manager = order_manager
        self.market_data_manager = market_data_manager
        self.prediction_engine = prediction_engine
        self.consumer = consumer
        self.producer = producer

    def init_application(self):
        try:
            self.consumer.subscribe([OrderManager.KAFKA_TOPIC])
            schedule.every().second.do(self.create_new_order)
            # schedule.every().second.do(self.check_unclosed_orders)
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

                prediction = self.prediction_engine.predict(asset.ticker_symbol, market_data)
                print(["PREDICT", prediction])
                # Buy at 2 percent more
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
                market_data = self.market_data_manager.get_latest_marketdata(asset)
                if market_data is None:
                    market_data = self.order_manager.get_market_data(asset.ticker_symbol, asset.exchange.value)

                price = market_data.close_price

                logging.warning([
                    f"Fetched price for ${asset.name} with ticker: ${asset.ticker_symbol} -> at {asset.exchange.value}",
                    price
                ])

                # TODO:
                # select a strategy, get focus price.
                # Query db based on criteria from strategy and aggregates a closed order.

                # min_closing_price\
                price = '0.000009724'
                closing_orders = self.order_manager.get_closing_orders(asset.ticker_symbol, price)
                print(closing_orders)
                # order = self.order_manager.close_order(
                #     ticker_symbol=asset.ticker_symbol,
                #     quantity=quantity,
                #     price=str(price),
                #     provider_name=asset.exchange.value
                # )

                # self.producer.send(OrderManager.KAFKA_TOPIC, order.model_dump_json())
            except Exception as exc:
                logging.error([
                    f"Error occurred finalizing asset ${asset.name} with ticker: ${asset.ticker_symbol} -> at {asset.exchange.value}",
                    exc
                ])
        print(["Threading..., sleeping...."])
        pass
