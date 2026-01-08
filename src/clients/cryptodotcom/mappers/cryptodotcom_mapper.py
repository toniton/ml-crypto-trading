from typing import Optional

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.mapper import Mapper
from api.interfaces.timeframe import Timeframe
from src.clients.cryptodotcom.cryptodotcom_dto import CryptoDotComInstrumentFeesResponseDto, \
    CryptoDotComMarketDataResponseDto, CryptoDotComCandleResponseDto, \
    CryptoDotComResponseOrderGetDto, CryptoDotComResponseOrderUpdateDto, \
    CryptoDotComUserBalanceResponseDto, \
    CryptoDotComUserFeesResponseDto
from src.core.interfaces.exchange_rest_client import ExchangeProvidersEnum


class CryptoDotComMapper(Mapper):
    provider = ExchangeProvidersEnum.CRYPTO_DOT_COM
    NANOSECONDS_PER_SECOND = 1_000_000_000

    @classmethod
    def to_marketdata(cls, data: CryptoDotComMarketDataResponseDto) -> Optional[MarketData]:
        return MarketData(
            close_price=data.result.data[0].a,
            low_price=data.result.data[0].l,
            high_price=data.result.data[0].h,
            volume=data.result.data[0].vv,
            timestamp=int(data.result.data[0].t) / cls.NANOSECONDS_PER_SECOND
        )

    @staticmethod
    def from_timeframe(data: Timeframe) -> Optional[str]:
        timeframe_map = {
            Timeframe.MIN1: "1m",
            Timeframe.MIN5: "5m",
            Timeframe.MIN15: "15m",
            Timeframe.MIN30: "30m",
            Timeframe.HOUR1: "1h",
            Timeframe.HOUR2: "2h",
            Timeframe.HOUR4: "4h",
            Timeframe.HOUR12: "12h",
            Timeframe.DAY1: "1D",
            Timeframe.DAY7: "7D",
            Timeframe.MON1: "1M",
        }
        return timeframe_map.get(data)

    @staticmethod
    def to_candles(response: CryptoDotComCandleResponseDto) -> list[Candle]:
        return list(
            map(
                lambda x: Candle(open=x.o, close=x.c, low=x.l, high=x.h, start_time=x.t),
                response.result.data
            )
        )

    @staticmethod
    def to_account_balance(response: CryptoDotComUserBalanceResponseDto) -> list[AccountBalance]:
        return [
            AccountBalance(
                currency=balance.instrument_name,
                available_balance=float(balance.max_withdrawal_balance or 0.0)
            )
            for balance in response.result.data[0].position_balances
        ] if response.result else []

    @staticmethod
    def to_fees(
            response: CryptoDotComUserFeesResponseDto
    ) -> Fees:
        return Fees(
            maker_fee_pct=float(response.result.effective_spot_maker_rate_bps) * 0.01,
            taker_fee_pct=float(response.result.effective_spot_taker_rate_bps) * 0.01,
        )

    @staticmethod
    def to_instrument_fees(
            response: CryptoDotComInstrumentFeesResponseDto
    ) -> Fees:
        return Fees(
            maker_fee_pct=float(response.result.effective_maker_rate_bps) * 0.01,
            taker_fee_pct=float(response.result.effective_taker_rate_bps) * 0.01,
        )

    @staticmethod
    def from_exchange_status(status: str) -> Optional[str]:
        status_map = {
            "NEW": OrderStatus.PENDING,
            "PENDING": OrderStatus.PENDING,
            "ACTIVE": OrderStatus.PROCESSING,
            "CANCELED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.CANCELLED,
            "EXPIRED": OrderStatus.CANCELLED,
            "FILLED": OrderStatus.COMPLETED,
        }
        return status_map.get(status)

    @classmethod
    def to_order(
            cls,
            response: CryptoDotComResponseOrderGetDto
    ) -> Order:
        return Order(
            uuid=response.result.client_oid,
            trade_action=TradeAction.BUY if response.result.side == "BUY" else TradeAction.SELL,
            quantity=response.result.quantity,
            provider_name=CryptoDotComMapper.provider.value,
            ticker_symbol=response.result.instrument_name,
            price=response.result.limit_price,
            created_time=int(response.result.create_time_ns) / cls.NANOSECONDS_PER_SECOND,
            status=CryptoDotComMapper.from_exchange_status(response.result.status)
        )

    @classmethod
    def to_orders(
            cls,
            response: CryptoDotComResponseOrderUpdateDto
    ) -> list[Order]:
        return [
            Order(
                uuid=order.client_oid,
                trade_action=TradeAction.BUY if order.side == "BUY" else TradeAction.SELL,
                quantity=order.quantity,
                provider_name=CryptoDotComMapper.provider.value,
                ticker_symbol=order.instrument_name,
                price=order.limit_price,
                created_time=int(order.create_time_ns) / cls.NANOSECONDS_PER_SECOND,
                status=CryptoDotComMapper.from_exchange_status(order.status)
            )
            for order in response.result.data
        ] if response.result else []
