from __future__ import annotations

import threading
from decimal import Decimal
from typing import Optional

from api.interfaces.asset import Asset
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from src.core.interfaces.event_bus import EventBus
from src.events.message_event_bus import CallbackSubscription
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.events import (
    BalanceChangedEvent,
    MarketDataEvent,
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderRejectedEvent,
    OrderSubmittedEvent,
)
from src.trading.protection.quote_portfolio import QuotePortfolio


class PortfolioRiskManager(ApplicationLoggingMixin):
    """Manages multi-asset portfolio risk, shared quote currency cash reservations,

    mark-to-market total equity, portfolio drawdown, and concentration limits.
    """

    def __init__(
            self,
            assets: Optional[list[Asset]] = None,
            event_bus: Optional[EventBus] = None,
            max_portfolio_drawdown: Optional[Decimal] = None,
            max_asset_concentration: Optional[Decimal] = None,
    ):
        self._lock = threading.RLock()
        self.portfolios: dict[tuple[str, str], QuotePortfolio] = {}
        self.max_portfolio_drawdown = (
            Decimal(str(max_portfolio_drawdown)) if max_portfolio_drawdown is not None else None
        )
        self.max_asset_concentration = (
            Decimal(str(max_asset_concentration)) if max_asset_concentration is not None else None
        )
        self._event_bus = event_bus
        self._subscriptions: list[str] = []

        if assets:
            for asset in assets:
                self.register_asset(asset)

        if event_bus is not None:
            self.subscribe(event_bus)

    def register_asset(self, asset: Asset) -> None:
        key = (asset.exchange.value, asset.quote_ticker_symbol)
        with self._lock:
            if key not in self.portfolios:
                self.portfolios[key] = QuotePortfolio(
                    exchange=asset.exchange.value,
                    quote_currency=asset.quote_ticker_symbol,
                )

    def get_portfolio(self, exchange: str, quote_currency: str) -> QuotePortfolio:
        key = (exchange, quote_currency)
        with self._lock:
            if key not in self.portfolios:
                self.portfolios[key] = QuotePortfolio(exchange=exchange, quote_currency=quote_currency)
            return self.portfolios[key]

    def subscribe(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._subscriptions.extend([
            event_bus.subscribe(OrderSubmittedEvent.__name__, CallbackSubscription(self._on_order_submitted)),
            event_bus.subscribe(OrderFilledEvent.__name__, CallbackSubscription(self._on_order_filled)),
            event_bus.subscribe(OrderCancelledEvent.__name__, CallbackSubscription(self._on_order_cancelled)),
            event_bus.subscribe(OrderRejectedEvent.__name__, CallbackSubscription(self._on_order_rejected)),
            event_bus.subscribe(MarketDataEvent.__name__, CallbackSubscription(self._on_market_data)),
            event_bus.subscribe(BalanceChangedEvent.__name__, CallbackSubscription(self._on_balance_changed)),
        ])

    def update_cash_balance(self, exchange: str, quote_currency: str, balance: Decimal) -> None:
        with self._lock:
            portfolio = self.get_portfolio(exchange, quote_currency)
            target_dec = Decimal(str(balance))
            if portfolio.total_cash != target_dec:
                portfolio.update_cash(target_dec)

    def update_market_data(self, asset: Asset, market_data: MarketData) -> None:
        with self._lock:
            portfolio = self.get_portfolio(asset.exchange.value, asset.quote_ticker_symbol)
            portfolio.update_asset_mark_price(asset.ticker_symbol, Decimal(str(market_data.close_price)))

    def update_position(self, asset: Asset, position_qty: Decimal) -> None:
        with self._lock:
            portfolio = self.get_portfolio(asset.exchange.value, asset.quote_ticker_symbol)
            portfolio.update_asset_position(asset.ticker_symbol, Decimal(str(position_qty)))

    def reserve_order_cash(self, asset: Asset, order_uuid: str, amount: Decimal) -> bool:
        with self._lock:
            portfolio = self.get_portfolio(asset.exchange.value, asset.quote_ticker_symbol)
            return portfolio.reserve_cash(order_uuid, amount)

    def release_order_cash(self, exchange: str, quote_currency: str, order_uuid: str) -> Decimal:
        with self._lock:
            portfolio = self.get_portfolio(exchange, quote_currency)
            return portfolio.release_cash(order_uuid)

    def release_order_cash_by_uuid(self, order_uuid: str) -> Decimal:
        with self._lock:
            for portfolio in self.portfolios.values():
                released = portfolio.release_cash(order_uuid)
                if released > Decimal("0"):
                    return released
            return Decimal("0")

    def can_trade(
            self,
            asset: Asset,
            trade_action: TradeAction,
            proposed_order_cost: Decimal,
            market_data: Optional[MarketData] = None,
    ) -> tuple[bool, Optional[str]]:
        if trade_action == TradeAction.SELL:
            return True, None

        with self._lock:
            portfolio = self.get_portfolio(asset.exchange.value, asset.quote_ticker_symbol)
            if market_data is not None:
                portfolio.update_asset_mark_price(asset.ticker_symbol, Decimal(str(market_data.close_price)))

            cost_dec = Decimal(str(proposed_order_cost))
            if cost_dec > portfolio.available_cash:
                reason = (
                    f"Insufficient unreserved cash in {portfolio.quote_currency} portfolio: "
                    f"required {cost_dec}, available {portfolio.available_cash} "
                    f"(total cash {portfolio.total_cash}, reserved {portfolio.reserved_cash})"
                )
                self.app_logger.warning(reason)
                return False, reason

            if self.max_portfolio_drawdown is not None:
                current_dd = portfolio.get_drawdown()
                max_dd = -abs(self.max_portfolio_drawdown)
                if current_dd < max_dd:
                    reason = (
                        f"Portfolio drawdown limit exceeded for {portfolio.quote_currency}: "
                        f"current {current_dd:.2%}, limit {max_dd:.2%}"
                    )
                    self.app_logger.warning(reason)
                    return False, reason

            if self.max_asset_concentration is not None:
                current_notional = portfolio.get_asset_notional(asset.ticker_symbol)
                projected_notional = current_notional + cost_dec
                total_equity = portfolio.get_total_equity()
                if total_equity > Decimal("0"):
                    projected_conc = projected_notional / total_equity
                    if projected_conc > self.max_asset_concentration:
                        reason = (
                            f"Asset concentration limit exceeded for {asset.ticker_symbol}: "
                            f"projected {projected_conc:.2%}, limit {self.max_asset_concentration:.2%}"
                        )
                        self.app_logger.warning(reason)
                        return False, reason

            return True, None

    def _on_order_submitted(self, event: OrderSubmittedEvent) -> None:
        if event.order and event.order.trade_action == TradeAction.BUY:
            price = event.order.fill_price or event.order.price
            qty = Decimal(str(event.order.quantity))
            cost = price * qty
            quote = event.order.ticker_symbol.split("_")[-1] if "_" in event.order.ticker_symbol else None
            with self._lock:
                for (exchange, quote_currency), portfolio in self.portfolios.items():
                    if exchange == event.order.provider_name:
                        if quote is None or quote == quote_currency:
                            if event.order.uuid not in portfolio.open_orders:
                                portfolio.reserve_cash(event.order.uuid, cost)
                            break

    def _on_order_filled(self, event: OrderFilledEvent) -> None:
        if event.order:
            self.release_order_cash_by_uuid(event.order.uuid)

    def _on_order_cancelled(self, event: OrderCancelledEvent) -> None:
        if event.order:
            self.release_order_cash_by_uuid(event.order.uuid)

    def _on_order_rejected(self, event: OrderRejectedEvent) -> None:
        if event.order:
            self.release_order_cash_by_uuid(event.order.uuid)

    def _on_market_data(self, event: MarketDataEvent) -> None:
        with self._lock:
            for portfolio in self.portfolios.values():
                if event.ticker_symbol in portfolio.asset_positions or event.ticker_symbol in portfolio.asset_mark_prices:
                    portfolio.update_asset_mark_price(
                        event.ticker_symbol, Decimal(str(event.market_data.close_price))
                    )

    def _on_balance_changed(self, event: BalanceChangedEvent) -> None:
        with self._lock:
            for (exchange, quote_currency), portfolio in self.portfolios.items():
                if event.exchange and exchange.upper() != event.exchange.upper():
                    continue
                if quote_currency.upper() == event.currency.upper():
                    target_total = event.total if event.total is not None else event.available
                    target_total_dec = Decimal(str(target_total))
                    if portfolio.total_cash != target_total_dec:
                        portfolio.update_cash(target_total_dec)
                        self.app_logger.info(
                            "Updated quote portfolio [%s / %s] cash balance to %s (source: %s)",
                            exchange,
                            quote_currency,
                            target_total,
                            event.source,
                        )
