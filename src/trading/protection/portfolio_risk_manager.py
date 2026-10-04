from __future__ import annotations

import threading
from decimal import Decimal
from typing import Optional

from api.interfaces.asset import Asset
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from src.configuration.portfolio_config import (
    PortfolioConfig,
    PortfolioExposureConfig,
    QuotePortfolioGuardConfig,
)
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
from src.trading.protection.portfolio_policy_resolver import (
    EffectivePortfolioConfig,
    PortfolioPolicyResolver,
)
from src.trading.protection.quote_portfolio import QuotePortfolio
from src.trading.protection.quote_portfolio_guard import (
    PortfolioRiskMetrics,
    QuotePortfolioGuard,
)
from src.trading.regimes.market_regime import MarketRegime


class PortfolioRiskManager(ApplicationLoggingMixin):
    """Manages multi-asset quote portfolios, tracks risk metrics, and gates trade execution."""

    def __init__(
            self,
            assets: Optional[list[Asset]] = None,
            event_bus: Optional[EventBus] = None,
            portfolio_config: Optional[PortfolioConfig] = None,
            max_portfolio_drawdown: Optional[Decimal] = None,
            max_asset_concentration: Optional[Decimal] = None,
    ):
        self._lock = threading.RLock()
        self.portfolios: dict[tuple[str, str], QuotePortfolio] = {}
        self.portfolio_config = portfolio_config or PortfolioConfig()
        self._explicit_drawdown = (
            Decimal(str(max_portfolio_drawdown)) if max_portfolio_drawdown is not None else None
        )
        self._explicit_concentration = (
            Decimal(str(max_asset_concentration)) if max_asset_concentration is not None else None
        )
        self._event_bus = event_bus
        self._subscriptions: list[str] = []

        if assets:
            for asset in assets:
                self.register_asset(asset)

        if event_bus is not None:
            self.subscribe(event_bus)

    @property
    def max_portfolio_drawdown(self) -> Optional[Decimal]:
        return self._explicit_drawdown or self.portfolio_config.guard.max_drawdown

    @property
    def max_asset_concentration(self) -> Optional[Decimal]:
        return self._explicit_concentration or self.portfolio_config.exposure.max_per_asset

    def update_config(self, portfolio_config: PortfolioConfig) -> None:
        with self._lock:
            self.portfolio_config = portfolio_config
            self.app_logger.info("PortfolioRiskManager configuration updated.")

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

    def reconcile_open_orders(self, active_order_uuids: set[str]) -> Decimal:
        with self._lock:
            released = Decimal("0")
            for portfolio in self.portfolios.values():
                released += portfolio.reconcile_orders(active_order_uuids)
            return released

    def get_risk_metrics(self, asset: Asset) -> PortfolioRiskMetrics:
        with self._lock:
            portfolio = self.get_portfolio(asset.exchange.value, asset.quote_ticker_symbol)
            total_cash = portfolio.total_cash
            reserved_cash = portfolio.reserved_cash
            available_cash = portfolio.available_cash
            invested_notional = portfolio.get_total_holdings_notional()
            total_equity = portfolio.get_total_equity()
            total_exposure_pct = (
                invested_notional / total_equity if total_equity > Decimal("0") else Decimal("0")
            )
            asset_notional = portfolio.get_asset_notional(asset.ticker_symbol)
            asset_concentration_pct = (
                asset_notional / total_equity if total_equity > Decimal("0") else Decimal("0")
            )
            peak_equity = portfolio.peak_equity
            drawdown_pct = portfolio.get_drawdown()
            open_position_count = sum(1 for qty in portfolio.asset_positions.values() if qty > Decimal("0"))

            return PortfolioRiskMetrics(
                total_equity=total_equity,
                total_cash=total_cash,
                reserved_cash=reserved_cash,
                available_cash=available_cash,
                invested_notional=invested_notional,
                total_exposure_pct=total_exposure_pct,
                asset_notional=asset_notional,
                asset_concentration_pct=asset_concentration_pct,
                peak_equity=peak_equity,
                drawdown_pct=drawdown_pct,
                daily_loss_pct=Decimal("0"),
                open_position_count=open_position_count,
            )

    def can_trade(
            self,
            asset: Asset,
            trade_action: TradeAction,
            proposed_order_cost: Decimal,
            market_data: Optional[MarketData] = None,
            regime: Optional[MarketRegime] = None,
    ) -> tuple[bool, Optional[str]]:
        if trade_action == TradeAction.SELL:
            return True, None

        with self._lock:
            portfolio = self.get_portfolio(asset.exchange.value, asset.quote_ticker_symbol)
            if market_data is not None:
                portfolio.update_asset_mark_price(asset.ticker_symbol, Decimal(str(market_data.close_price)))

            risk_metrics = self.get_risk_metrics(asset)
            effective_config = PortfolioPolicyResolver.resolve(self.portfolio_config, asset)

            if self._explicit_drawdown is not None or self._explicit_concentration is not None:
                effective_config = EffectivePortfolioConfig(
                    exposure=PortfolioExposureConfig(
                        max_total=effective_config.exposure.max_total,
                        max_per_asset=(
                            self._explicit_concentration
                            if self._explicit_concentration is not None
                            else effective_config.exposure.max_per_asset
                        ),
                        max_per_quote=effective_config.exposure.max_per_quote,
                    ),
                    regime=effective_config.regime,
                    guard=QuotePortfolioGuardConfig(
                        enabled=effective_config.guard.enabled,
                        max_drawdown=(
                            self._explicit_drawdown
                            if self._explicit_drawdown is not None
                            else effective_config.guard.max_drawdown
                        ),
                        max_daily_loss=effective_config.guard.max_daily_loss,
                        max_position_count=effective_config.guard.max_position_count,
                        min_quote_reserve=effective_config.guard.min_quote_reserve,
                        max_quote_exposure=effective_config.guard.max_quote_exposure,
                    ),
                )

            current_regime = regime or MarketRegime.UNKNOWN
            decision = QuotePortfolioGuard.evaluate(
                asset_symbol=asset.ticker_symbol,
                order_cost=Decimal(str(proposed_order_cost)),
                risk=risk_metrics,
                regime=current_regime,
                config=effective_config,
            )

            if not decision.allowed:
                self.app_logger.warning(
                    "Trade disallowed for %s: %s", asset.ticker_symbol, decision.reason
                )
                return False, decision.reason

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
                    target_cash = event.available if event.available is not None else event.total
                    target_cash_dec = Decimal(str(target_cash))
                    if portfolio.total_cash != target_cash_dec:
                        portfolio.update_cash(target_cash_dec)
                        self.app_logger.info(
                            "Updated quote portfolio [%s / %s] cash balance to %s (source: %s)",
                            exchange,
                            quote_currency,
                            target_cash,
                            event.source,
                        )
