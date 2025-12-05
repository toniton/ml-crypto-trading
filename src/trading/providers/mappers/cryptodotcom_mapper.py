from typing import Optional

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.core.interfaces.exchange_provider import ExchangeProvidersEnum
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.mapper import Mapper
from api.interfaces.timeframe import Timeframe
from src.trading.providers.cryptodotcom_dto import CryptoDotComInstrumentFeesResponseDto, \
    CryptoDotComMarketDataResponseDto, CryptoDotComCandleResponseDto, \
    CryptoDotComResponseOrderUpdateDto, CryptoDotComUserBalanceResponseDto, CryptoDotComUserFeesResponseDto


class CryptoDotComMapper(Mapper):
    provider = ExchangeProvidersEnum.CRYPTO_DOT_COM

    @staticmethod
    def to_marketdata(data: CryptoDotComMarketDataResponseDto) -> Optional[MarketData]:
        return MarketData(
            close_price=data.result.data[0].a,
            low_price=data.result.data[0].l,
            high_price=data.result.data[0].h,
            volume=data.result.data[0].vv,
            timestamp=data.result.data[0].t
        )

    @staticmethod
    def from_timeframe(data: Timeframe) -> Optional[str]:
        if data == Timeframe.MIN1:
            return "1m"
        elif data == Timeframe.MIN5:
            return "5m"
        elif data == Timeframe.MIN15:
            return "15m"
        elif data == Timeframe.MIN30:
            return "30m"
        elif data == Timeframe.HOUR1:
            return "1h"
        elif data == Timeframe.HOUR2:
            return "2h"
        elif data == Timeframe.HOUR4:
            return "4h"
        elif data == Timeframe.HOUR12:
            return "12h"
        elif data == Timeframe.DAY1:
            return "1D"
        elif data == Timeframe.DAY7:
            return "7D"
        elif data == Timeframe.MON1:
            return "1M"
        return None

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
    def to_orders(
            response: CryptoDotComResponseOrderUpdateDto
    ) -> list[Order]:
        return [
            Order(
                uuid=order.order_id,
                trade_action=TradeAction.BUY if order.side == "BUY" else TradeAction.SELL,
                quantity=order.quantity,
                provider_name=CryptoDotComMapper.provider.value,
                ticker_symbol=order.instrument_name,
                price=order.limit_price,
                created_time=order.create_time
            )
            for order in response.result.data
        ] if response.result else []
