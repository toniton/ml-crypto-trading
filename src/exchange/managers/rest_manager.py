import functools
import time
from decimal import Decimal
from typing import Any, List, Optional
from urllib.error import HTTPError

from cachetools import cached, TTLCache
from circuitbreaker import circuit, CircuitBreakerError, CircuitBreakerMonitor

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from src.exchange.interfaces.exchange_rest_manager import ExchangeRestManager
from src.exchange.registries.rest_registry import RestRegistry
from src.metrics.collectors.exchange_metrics_collector import ExchangeMetricsCollector


def _instrument_rest(operation: str):
    def decorator(func):
        cb_name = func.__qualname__

        @functools.wraps(func)
        def wrapper(self, exchange: str, *args, **kwargs):
            collector = getattr(self, "_metrics_collector", None)
            if collector is None:
                return func(self, exchange, *args, **kwargs)

            cb = CircuitBreakerMonitor.get(cb_name)
            was_opened = cb.opened if cb else False
            start_time = time.perf_counter()
            collector.record_request(exchange, operation)
            try:
                result = func(self, exchange, *args, **kwargs)
                return result
            except CircuitBreakerError as cbe:
                collector.record_circuit_trip(exchange, operation)
                collector.record_error(exchange, operation, "CircuitBreakerError")
                raise cbe
            except Exception as exc:
                collector.record_error(exchange, operation, type(exc).__name__)
                if cb and not was_opened and cb.opened:
                    collector.record_circuit_trip(exchange, operation)
                raise exc
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000
                collector.record_duration(exchange, operation, duration_ms)

        return wrapper

    return decorator


class RestManager(ExchangeRestManager, RestRegistry):
    def __init__(self, metrics_collector: Optional[ExchangeMetricsCollector] = None):
        super().__init__()
        self._metrics_collector = metrics_collector

    @_instrument_rest("get_market_data")
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_market_data(self, exchange: str, ticker_symbol: str) -> MarketData:
        service = self.get_service(exchange)
        builder = service.builder().market_data(ticker_symbol)
        return service.execute(builder)

    @cached(cache=TTLCache(maxsize=1024, ttl=600))
    @_instrument_rest("get_account_balance")
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_account_balance(self, exchange: str) -> List[AccountBalance]:
        service = self.get_service(exchange)
        builder = service.builder().account_balance()
        return service.execute(builder)

    @cached(cache=TTLCache(maxsize=1024, ttl=6000))
    @_instrument_rest("get_account_fees")
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_account_fees(self, exchange: str) -> Fees:
        service = self.get_service(exchange)
        builder = service.builder().account_fees()
        return service.execute(builder)

    @cached(cache=TTLCache(maxsize=1024, ttl=6000))
    @_instrument_rest("get_instrument_fees")
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_instrument_fees(self, exchange: str, ticker_symbol: str) -> Fees:
        service = self.get_service(exchange)
        builder = service.builder().instrument_fees(ticker_symbol)
        return service.execute(builder)

    @_instrument_rest("get_order")
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_order(self, exchange: str, uuid: str) -> Any:
        service = self.get_service(exchange)
        builder = service.builder().get_order(uuid)
        return service.execute(builder)

    @_instrument_rest("get_open_orders")
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_open_orders(self, exchange: str, ticker_symbol: str = None) -> List[Order]:
        service = self.get_service(exchange)
        builder = service.builder().get_open_orders(ticker_symbol)
        return service.execute(builder)

    @_instrument_rest("place_order")
    def place_order(
            self,
            exchange: str,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: Decimal,
            trade_action: TradeAction,
            created_time: Optional[float] = None,
    ) -> None:
        service = self.get_service(exchange)
        builder = service.builder().create_order(
            uuid, ticker_symbol, quantity, price, trade_action, created_time
        )
        service.execute(builder)

    @_instrument_rest("cancel_order")
    def cancel_order(self, exchange: str, uuid: str) -> None:
        service = self.get_service(exchange)
        builder = service.builder().cancel_order(uuid)
        service.execute(builder)

    @_instrument_rest("get_candles")
    @circuit(failure_threshold=5, expected_exception=(HTTPError, RuntimeError), recovery_timeout=60)
    def get_candles(self, exchange: str, ticker_symbol: str, timeframe: Timeframe) -> List[Candle]:
        service = self.get_service(exchange)
        builder = service.builder().candles(ticker_symbol, timeframe)
        return service.execute(builder)

