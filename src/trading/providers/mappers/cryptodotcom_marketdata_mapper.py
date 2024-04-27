from typing import Optional

from api.interfaces.exchange_provider import ExchangeProvidersEnum
from api.interfaces.market_data import MarketData
from api.interfaces.mapper import Mapper
from src.trading.providers.cryptodotcom_dto import CryptoDotComMarketDataResponseDto


class CryptoDotComMarketDataMapper(Mapper):
    provider = ExchangeProvidersEnum.CRYPTO_DOT_COM

    @staticmethod
    def map(data: dict) -> Optional[MarketData]:
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
