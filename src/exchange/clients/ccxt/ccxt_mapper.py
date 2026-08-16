from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.core.interfaces.mapper import Mapper


class CCXTBaseMapper:
    @staticmethod
    def _map_status(status: str) -> OrderStatus:
        mapping = {
            'open': OrderStatus.PENDING,
            'closed': OrderStatus.COMPLETED,
            'canceled': OrderStatus.CANCELLED,
            'expired': OrderStatus.CANCELLED,
            'rejected': OrderStatus.CANCELLED
        }
        return mapping.get(status, OrderStatus.PENDING)


class CCXTTickerMapper(Mapper[Dict[str, Any], MarketData], CCXTBaseMapper):
    def map(self, source: Dict[str, Any]) -> MarketData:
        return MarketData(
            volume=Decimal(str(source.get('baseVolume', 0))),
            high_price=Decimal(str(source.get('high', 0))),
            low_price=Decimal(str(source.get('low', 0))),
            close_price=Decimal(str(source.get('close', 0))),
            timestamp=source.get('timestamp', 0) / 1000.0 if source.get('timestamp') else 0
        )


class CCXTCandleMapper(Mapper[List[Any], Candle], CCXTBaseMapper):
    def map(self, source: List[Any]) -> list[Candle]:
        # CCXT OHLCV format: [timestamp, open, high, low, close, volume]
        if not source or (source and len(source) == 0):
            return []

        if source and isinstance(source, dict):
            return [
                Candle(
                    start_time=source['timestamp'] / 1000.0,
                    open=Decimal(source['open']),
                    high=Decimal(source['high']),
                    low=Decimal(source['low']),
                    close=Decimal(source['close'])
                )
            ]

        return [
            Candle(
                start_time=x[0] / 1000.0,
                open=Decimal(str(x[1])),
                high=Decimal(str(x[2])),
                low=Decimal(str(x[3])),
                close=Decimal(str(x[4]))
            )
            for x in source
        ]


class CCXTAccountBalanceMapper(Mapper[Dict[str, Any], List[AccountBalance]], CCXTBaseMapper):
    def map(self, source: Dict[str, Any]) -> List[AccountBalance]:
        balances: List[AccountBalance] = []
        info = source.get("info", {})
        for balance in info.get("balances", []):
            currency = balance.get("asset")
            free_balance = Decimal(str(balance.get("free", "0")))

            if free_balance <= Decimal("0"):
                continue

            balances.append(
                AccountBalance(
                    currency=currency,
                    available_balance=free_balance
                )
            )
        return balances


class CCXTOrderMapper(Mapper[Dict[str, Any], Order], CCXTBaseMapper):
    def __init__(self, provider_name: str):
        self._provider_name = provider_name

    def map(self, source: Dict[str, Any]) -> Order:
        return Order(
            uuid=source.get('clientOrderId') or source.get('id'),
            provider_name=self._provider_name,
            ticker_symbol=source.get('symbol'),
            price=Decimal(str(source.get('price', 0))),
            quantity=str(source.get('amount', 0)),
            trade_action=TradeAction(source.get('side').upper()),
            created_time=source.get('timestamp', 0) / 1000.0,
            status=self._map_status(source.get('status'))
        )


class CCXTOpenOrdersMapper(Mapper[List[Dict[str, Any]], List[Order]], CCXTBaseMapper):
    def __init__(self, provider_name: str):
        self._provider_name = provider_name

    def map(self, source: List[Dict[str, Any]]) -> List[Order]:
        return [
            CCXTOrderMapper(self._provider_name).map(item)
            for item in source
        ]


class CCXTTimeframe:
    MAP = {
        Timeframe.MIN1: "1m",
        Timeframe.MIN5: "5m",
        Timeframe.MIN15: "15m",
        Timeframe.MIN30: "30m",
        Timeframe.HOUR1: "1h",
        Timeframe.HOUR2: "2h",
        Timeframe.HOUR4: "4h",
        Timeframe.HOUR12: "12h",
        Timeframe.DAY1: "1d",
        Timeframe.DAY7: "1w",
        Timeframe.MON1: "1M",
    }


class CCXTFeesMapper(Mapper[Dict[str, Any], Optional[Fees]], CCXTBaseMapper):
    def map(self, source: Dict[str, Any]) -> Optional[Fees]:
        maker = source.get("maker")
        taker = source.get("taker")

        if maker is None or taker is None:
            return None

        return Fees(
            maker_fee_pct=Decimal(maker) * Decimal(100),
            taker_fee_pct=Decimal(taker) * Decimal(100)
        )


class CCXTMapperFactory:
    _MAPPER_REGISTRY: dict[str, type] = {
        'ticker': CCXTTickerMapper,
        'ohlcv': CCXTCandleMapper,
        'balance': CCXTAccountBalanceMapper,
        'orders': CCXTOrderMapper,
        'open_orders': CCXTOpenOrdersMapper,
        'fees': CCXTFeesMapper,
    }

    @classmethod
    def get_mapper(cls, subscription_type: str, provider_name: str | None = None) -> Mapper | None:
        mapper_class = cls._MAPPER_REGISTRY.get(subscription_type)
        if not mapper_class:
            return None

        if subscription_type in ('orders', 'open_orders') and provider_name:
            return mapper_class(provider_name)
        if subscription_type in ('orders', 'open_orders'):
            raise ValueError(f"provider_name is required for '{subscription_type}' mapper")

        return mapper_class()
