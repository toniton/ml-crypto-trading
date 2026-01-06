import copy
from typing import List
from collections import defaultdict
from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus
from src.core.interfaces.trading_journal import TradingJournal


class InMemoryTradingJournal(TradingJournal):
    def __init__(self):
        self._entries: List[Order] = []
        self._entries_by_ticker: dict[str, List[Order]] = defaultdict(list)
        self._recorded_order_ids: set[str] = set()

    def record_fill(self, order: Order) -> None:
        if order.status != OrderStatus.COMPLETED:
            return

        if order.uuid in self._recorded_order_ids:
            return

        order_copy = copy.deepcopy(order)
        self._entries.append(order_copy)
        self._entries_by_ticker[order.ticker_symbol].append(order_copy)
        self._recorded_order_ids.add(order.uuid)

    def entries(self, ticker_symbol: str = None) -> List[Order]:
        if ticker_symbol:
            return list(self._entries_by_ticker[ticker_symbol])
        return list(self._entries)
