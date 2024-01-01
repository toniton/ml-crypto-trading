from typing import Optional, Any

from entities.market_data import MarketData
from trading.mappers.mapper import Mapper
from trading.providers.cryptodotcom_dto import CryptoDotComWebsocketMarketDataResponseDto


class CryptoDotComMarketDataMapper(Mapper):
    @staticmethod
    def map(data: Any) -> Optional[MarketData]:
        if data["method"] == "subscribe":
            data = CryptoDotComWebsocketMarketDataResponseDto(**data)
            return MarketData(
                close_price=data.result.data[0].c
            )
        return None
