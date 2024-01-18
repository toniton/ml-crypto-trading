from typing import Optional, Any

from entities.market_data import MarketData
from trading.mappers.mapper import Mapper
from trading.providers.cryptodotcom_dto import CryptoDotComMarketDataResponseDto


class CryptoDotComMarketDataMapper(Mapper):
    @staticmethod
    def map(data: dict) -> Optional[MarketData]:
        data = CryptoDotComMarketDataResponseDto(**data)
        return MarketData(
            close_price=data.result.data[0].a,
            low_price=data.result.data[0].l,
            high_price=data.result.data[0].h,
            volume=data.result.data[0].vv,
            timestamp=data.result.data[0].t
        )
