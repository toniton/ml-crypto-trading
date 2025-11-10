from typing import Optional

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.exchange_provider import ExchangeProvidersEnum
from api.interfaces.market_data import MarketData
from api.interfaces.mapper import Mapper
from api.interfaces.timeframe import Timeframe
from src.trading.providers.cryptodotcom_dto import CryptoDotComMarketDataResponseDto, CryptoDotComCandleResponseDto, \
    CryptoDotComUserBalanceResponseDto


class CryptoDotComMapper(Mapper):
    provider = ExchangeProvidersEnum.CRYPTO_DOT_COM

    @staticmethod
    def to_marketdata(data: dict) -> Optional[MarketData]:
        if data["method"] == "subscribe" or data["method"] == "public/get-tickers":
            data = CryptoDotComMarketDataResponseDto(**data)
            return MarketData(
                close_price=data.result.data[0].a,
                low_price=data.result.data[0].l,
                high_price=data.result.data[0].h,
                volume=data.result.data[0].vv,
                timestamp=data.result.data[0].t
            )
        return None

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
    def to_account_balance(
            base_ticker_symbol: str, quote_ticker_symbol: str,
            response: CryptoDotComUserBalanceResponseDto
    ) -> AccountBalance:
        balances = {
            p.instrument_name: float(p.max_withdrawal_balance or 0.0)
            for p in response.result.data[0].position_balances
        }
        return AccountBalance(
            available_balance=balances.get(quote_ticker_symbol, 0.0),
            position_balance=balances.get(base_ticker_symbol, 0.0),
        )
