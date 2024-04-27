from typing import Callable

from api.interfaces.order import Order


class OrderHelper:
    @staticmethod
    def less_than_price_filter(price: str) -> Callable:
        def price_filter(order: Order) -> bool:
            return float(price) > float(order.price)

        return price_filter
