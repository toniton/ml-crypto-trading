import json
import logging
import threading
import time

import schedule
from kafka import KafkaProducer, KafkaConsumer

from entities.asset import Asset
from entities.order import Order
from trading.orders.order_manager import OrderManager
from trading.predictions.prediction_engine import PredictionEngine


class TradingEngine:
    assets: list[Asset]
    consumer: KafkaConsumer
    order_manager: OrderManager
    prediction_engine: PredictionEngine

    def __init__(
        self,
        assets: list[Asset],
        consumer: KafkaConsumer,
        producer: KafkaProducer,
        order_manager: OrderManager,
        prediction_engine: PredictionEngine
    ):
        self.assets = assets
        self.order_manager = order_manager
        self.prediction_engine = prediction_engine
        self.consumer = consumer
        self.producer = producer

    def init_application(self):
        try:
            self.consumer.subscribe([OrderManager.KAFKA_TOPIC])
            schedule.every().second.do(self.create_new_order)
        except Exception as exc:
            logging.error(["Error occurred initializing application. ->", exc])

        schedule_thread = threading.Thread(target=self.run_pending_schedules)
        execute_thread = threading.Thread(target=self.execute_queued_orders)
        schedule_thread.start()
        execute_thread.start()
        # schedule_thread.join()
        # execute_thread.join()
        pass

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
            price = self.order_manager.get_price(asset.ticker_symbol, asset.exchange.value)
            logging.warning([
                f"Fetched price for ${asset.name} with ticker: ${asset.ticker_symbol} -> at {asset.exchange.value}",
                price
            ])

            order = self.order_manager.open_order(
                ticker_symbol=asset.ticker_symbol,
                quantity=1,
                price=float(price),
                provider_name=asset.exchange.value
            )

            self.producer.send(OrderManager.KAFKA_TOPIC, order.model_dump_json())

        pass

    def check_unclosed_orders(self):
        print(["Threading..., sleeping...."])
        pass
