from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List
from uuid import uuid4

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order, OrderStatus
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from backtest.backtest_clock import BacktestClock
from backtest.backtest_data_loader import BacktestDataLoader
from backtest.backtest_event_bus import BacktestEventBus
from backtest.events import BalanceUpdateEvent, OrderFillEvent
from src.core.interfaces.exchange_rest_client import ExchangeRestClient, ExchangeProvidersEnum


@dataclass
class SimulatedAccount:
    balance_usd: float = 10000.0
    positions: Dict[str, float] = field(default_factory=dict)
    orders: List[Order] = field(default_factory=list)


class BacktestExchangeRestClient(ExchangeRestClient):
    def __init__(
            self,
            clock: BacktestClock = None,
            event_bus: BacktestEventBus = None,
            data_loader: BacktestDataLoader = None,
    ):
        self.clock = clock
        self.loader = data_loader
        self.bus = event_bus
        self.account = SimulatedAccount()

    def get_provider_name(self) -> str:
        return ExchangeProvidersEnum.CRYPTO_DOT_COM.name

    def get_market_data(self, ticker_symbol: str) -> MarketData:
        current = self.clock.now(ticker_symbol)
        data = self.loader.get_data(ticker_symbol, current)
        return MarketData(
            timestamp=data.timestamp,
            volume=str(data.volume),
            low_price=str(data.low_price),
            high_price=str(data.high_price),
            close_price=str(data.close_price)
        )

    def get_account_balance(self) -> list[AccountBalance]:
        return [
            AccountBalance(
                currency="USD",
                available_balance=self.account.balance_usd,
            )
        ]

    def get_account_fees(self) -> Fees:
        return Fees(
            maker_fee_pct=0.0,
            taker_fee_pct=0.0
        )

    def get_instrument_fees(self, ticker_symbol: str) -> Fees:
        return Fees(
            maker_fee_pct=0.0,
            taker_fee_pct=0.0
        )

    def place_order(
            self,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: str,
            trade_action: TradeAction
    ) -> Order:
        order_uuid = uuid or str(uuid4())
        qty = float(quantity)
        prc = float(price)
        total_value = qty * prc

        if trade_action == TradeAction.BUY:
            if self.account.balance_usd < total_value:
                raise ValueError(
                    f"Insufficient balance: {self.account.balance_usd} < {total_value}"
                )
            self.account.balance_usd -= total_value
            self.account.positions[ticker_symbol] = (
                    self.account.positions.get(ticker_symbol, 0) + qty
            )
        else:
            current_position = self.account.positions.get(ticker_symbol, 0)
            if current_position < qty:
                raise ValueError(
                    f"Insufficient position: {current_position} < {qty}"
                )
            self.account.positions[ticker_symbol] -= qty
            self.account.balance_usd += total_value

        order = Order(
            uuid=order_uuid,
            ticker_symbol=ticker_symbol,
            quantity=quantity,
            price=price,
            status=OrderStatus.COMPLETED,
            provider_name=self.get_provider_name(),
            trade_action=trade_action,
            created_time=self.clock.now(ticker_symbol)
        )
        self.account.orders.append(order)

        logging.info(
            f"BacktestRestClient: {trade_action.name} {quantity} {ticker_symbol} @ {price} "
            f"(Balance: ${self.account.balance_usd:.2f})"
        )

        self.bus.publish(OrderFillEvent(order=order))

        balances = self.get_account_balance()
        self.bus.publish(BalanceUpdateEvent(balances=balances))

        return order

    def get_candle(self, ticker_symbol: str, timeframe: Timeframe) -> list[Candle]:
        market_data = self.get_market_data(ticker_symbol)
        return [
            Candle(
                open=market_data.close_price,
                high=market_data.high_price,
                low=market_data.low_price,
                close=market_data.close_price,
                start_time=float(market_data.timestamp)
            )
        ]

    def get_total_value(self) -> float:
        total = self.account.balance_usd
        for _ticker, qty in self.account.positions.items():
            try:
                if self._latest_market_data:
                    total += qty * float(self._latest_market_data.close_price)
            except (ValueError, AttributeError):
                pass
        return total
