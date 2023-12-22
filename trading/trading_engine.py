from entities.asset import Asset
from trading.orders.order_manager import OrderManager
from trading.predictions.prediction_engine import PredictionEngine


class TradingEngine:
    assets: tuple[Asset]
    order_manager: OrderManager
    prediction_engine: PredictionEngine

    def create_new_order(self):
        pass

    def check_unclosed_orders(self):
        pass
