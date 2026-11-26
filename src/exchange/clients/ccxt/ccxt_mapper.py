from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.instrument_metadata import InstrumentMetadata
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
        bid = source.get('bid')
        ask = source.get('ask')
        return MarketData(
            volume=Decimal(str(source.get('baseVolume', 0))),
            high_price=Decimal(str(source.get('high', 0))),
            low_price=Decimal(str(source.get('low', 0))),
            close_price=Decimal(str(source.get('close', 0))),
            timestamp=source.get('timestamp', 0) / 1000.0 if source.get('timestamp') else 0,
            bid_price=Decimal(str(bid)) if bid is not None else None,
            ask_price=Decimal(str(ask)) if ask is not None else None,
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
        status = self._map_status(source.get('status'))
        fee = source.get('fee')
        fees = Decimal(str(fee.get('cost', 0))) if fee and fee.get('cost') is not None else None
        avg = source.get('average')
        fill_price = Decimal(str(avg)) if avg is not None else None
        return Order(
            uuid=source.get('clientOrderId') or source.get('id'),
            provider_name=self._provider_name,
            ticker_symbol=source.get('symbol'),
            price=Decimal(str(source.get('price', 0))),
            quantity=str(source.get('amount', 0)),
            trade_action=TradeAction(source.get('side').upper()),
            created_time=source.get('timestamp', 0) / 1000.0,
            executed_time=(
                source.get('timestamp', 0) / 1000.0
                if status == OrderStatus.COMPLETED and source.get('timestamp')
                else None
            ),
            status=status,
            fees=fees,
            fill_price=fill_price,
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


class CCXTInstrumentMetadataMapper(
    Mapper[Dict[str, Any], Optional[InstrumentMetadata]], CCXTBaseMapper
):
    """Maps a CCXT market definition dictionary into InstrumentMetadata."""

    def __init__(self, provider_name: str):
        self._provider_name = provider_name

    def map(self, source: Dict[str, Any]) -> Optional[InstrumentMetadata]:
        if not isinstance(source, dict) or not source:
            return None
        precision = source.get("precision") or {}
        limits = source.get("limits") or {}
        amount_limits = limits.get("amount") or {}
        cost_limits = limits.get("cost") or {}
        price_limits = limits.get("price") or {}

        raw_amount_prec = precision.get("amount")
        raw_price_prec = precision.get("price")
        qty_precision = self._precision_to_decimals(raw_amount_prec, default=4)
        price_precision = self._precision_to_decimals(raw_price_prec, default=2)
        qty_step = (
            Decimal(str(raw_amount_prec))
            if isinstance(raw_amount_prec, float) and raw_amount_prec < 1
            else Decimal("1").scaleb(-qty_precision)
        )
        min_qty = (
            Decimal(str(amount_limits["min"]))
            if amount_limits.get("min") is not None
            else qty_step
        )
        min_notional = (
            Decimal(str(cost_limits["min"]))
            if cost_limits.get("min") is not None
            else None
        )
        min_price = (
            Decimal(str(price_limits["min"]))
            if price_limits.get("min") is not None
            else Decimal("1").scaleb(-price_precision)
        )
        symbol = str(source.get("symbol") or "").upper().replace("/", "_").replace("-", "_")
        return InstrumentMetadata(
            exchange=self._provider_name,
            symbol=symbol,
            quantity_precision=qty_precision,
            price_precision=price_precision,
            min_quantity=min_qty,
            quantity_step=qty_step,
            min_price=min_price,
            min_notional=min_notional,
        )

    @staticmethod
    def _precision_to_decimals(value: Any, default: int) -> int:
        if value is None:
            return default
        if isinstance(value, int):
            return max(value, 0)
        dec = Decimal(str(value)).normalize()
        exp = dec.as_tuple().exponent
        return abs(exp) if isinstance(exp, int) and exp < 0 else 0


class CCXTMapperFactory:
    _MAPPER_REGISTRY: dict[str, type] = {
        'ticker': CCXTTickerMapper,
        'ohlcv': CCXTCandleMapper,
        'balance': CCXTAccountBalanceMapper,
        'orders': CCXTOrderMapper,
        'open_orders': CCXTOpenOrdersMapper,
        'fees': CCXTFeesMapper,
        'instrument_metadata': CCXTInstrumentMetadataMapper,
    }

    @classmethod
    def get_mapper(cls, subscription_type: str, provider_name: str | None = None) -> Mapper | None:
        mapper_class = cls._MAPPER_REGISTRY.get(subscription_type)
        if not mapper_class:
            return None

        if subscription_type in ('orders', 'open_orders', 'instrument_metadata') and provider_name:
            return mapper_class(provider_name)
        if subscription_type in ('orders', 'open_orders', 'instrument_metadata'):
            raise ValueError(f"provider_name is required for '{subscription_type}' mapper")

        return mapper_class()
