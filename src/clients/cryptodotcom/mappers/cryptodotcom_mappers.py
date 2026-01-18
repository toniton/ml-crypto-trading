from decimal import Decimal
from typing import Optional

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.clients.cryptodotcom.cryptodotcom_dto import (
    CryptoDotComMarketDataResponseDto,
    CryptoDotComCandleResponseDto,
    CryptoDotComUserBalanceResponseDto,
    CryptoDotComUserFeesResponseDto,
    CryptoDotComInstrumentFeesResponseDto,
    CryptoDotComResponseOrderGetDto,
    CryptoDotComResponseOrderUpdateDto
)
from src.core.interfaces.exchange_rest_client import ExchangeProvidersEnum
from src.core.interfaces.mapper import Mapper


class CryptoDotComBaseMapper:
    NANOSECONDS_PER_SECOND = 1_000_000_000
    provider = ExchangeProvidersEnum.CRYPTO_DOT_COM

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


class CryptoDotComMarketDataMapper(Mapper[CryptoDotComMarketDataResponseDto, Optional[MarketData]],
                                   CryptoDotComBaseMapper):
    def map(self, source: dict) -> Optional[MarketData]:
        dto = CryptoDotComMarketDataResponseDto(**source)
        if not dto.result or not dto.result.data:
            return None
        data = dto.result.data[0]
        return MarketData(
            close_price=Decimal(data.a),
            low_price=Decimal(data.l),
            high_price=Decimal(data.h),
            volume=Decimal(data.vv),
            timestamp=int(data.t) / self.NANOSECONDS_PER_SECOND
        )


class CryptoDotComCandleMapper(Mapper[CryptoDotComCandleResponseDto, list[Candle]], CryptoDotComBaseMapper):
    def map(self, source: dict) -> list[Candle]:
        dto = CryptoDotComCandleResponseDto(**source)
        if not dto.result or not dto.result.data:
            return []

        return [
            Candle(open=Decimal(x.o), close=Decimal(x.c), low=Decimal(x.l), high=Decimal(x.h), start_time=x.t)
            for x in dto.result.data
        ]


class CryptoDotComAccountBalanceMapper(Mapper[CryptoDotComUserBalanceResponseDto, list[AccountBalance]],
                                       CryptoDotComBaseMapper):
    def map(self, source: dict) -> list[AccountBalance]:
        dto = CryptoDotComUserBalanceResponseDto(**source)
        if not dto.result or not dto.result.data:
            return []

        return [
            AccountBalance(
                currency=balance.instrument_name,
                available_balance=Decimal(balance.max_withdrawal_balance or 0.0)
            )
            for balance in dto.result.data[0].position_balances
        ]


class CryptoDotComFeesMapper(Mapper[CryptoDotComUserFeesResponseDto, Fees], CryptoDotComBaseMapper):
    def map(self, source: dict) -> Fees:
        dto = CryptoDotComUserFeesResponseDto(**source)
        # Assuming result is present based on DTO structure guarantees or adding check
        if not dto.result:
            # Fallback or appropriate error handling, but here assuming valid response flow
            return Fees(maker_fee_pct=Decimal(0), taker_fee_pct=Decimal(0))

        return Fees(
            maker_fee_pct=Decimal(dto.result.effective_spot_maker_rate_bps) * Decimal(0.01),
            taker_fee_pct=Decimal(dto.result.effective_spot_taker_rate_bps) * Decimal(0.01),
        )


class CryptoDotComInstrumentFeesMapper(Mapper[CryptoDotComInstrumentFeesResponseDto, Fees], CryptoDotComBaseMapper):
    def map(self, source: dict) -> Fees:
        dto = CryptoDotComInstrumentFeesResponseDto(**source)
        if not dto.result:
            return Fees(maker_fee_pct=Decimal(0), taker_fee_pct=Decimal(0))

        return Fees(
            maker_fee_pct=Decimal(dto.result.effective_maker_rate_bps) * Decimal(0.01),
            taker_fee_pct=Decimal(dto.result.effective_taker_rate_bps) * Decimal(0.01),
        )


class CryptoDotComOrderMapper(Mapper[CryptoDotComResponseOrderGetDto, Order], CryptoDotComBaseMapper):
    def map(self, source: dict) -> Order:
        dto = CryptoDotComResponseOrderGetDto(**source)
        result = dto.result
        return Order(
            uuid=result.client_oid,
            trade_action=TradeAction.BUY if result.side == "BUY" else TradeAction.SELL,
            quantity=result.quantity,
            provider_name=self.provider.value,
            ticker_symbol=result.instrument_name,
            price=Decimal(result.limit_price),
            created_time=int(result.create_time_ns) / self.NANOSECONDS_PER_SECOND,
            status=self.from_exchange_status(result.status)
        )


class CryptoDotComOrdersMapper(Mapper[CryptoDotComResponseOrderUpdateDto, list[Order]], CryptoDotComBaseMapper):
    def map(self, source: dict) -> list[Order]:
        dto = CryptoDotComResponseOrderUpdateDto(**source)
        if not dto.result or not dto.result.data:
            return []

        return [
            Order(
                uuid=order.client_oid,
                trade_action=TradeAction.BUY if order.side == "BUY" else TradeAction.SELL,
                quantity=order.quantity,
                provider_name=self.provider.value,
                ticker_symbol=order.instrument_name,
                price=Decimal(order.limit_price),
                created_time=int(order.create_time_ns) / self.NANOSECONDS_PER_SECOND,
                status=self.from_exchange_status(order.status)
            )
            for order in dto.result.data
        ]
