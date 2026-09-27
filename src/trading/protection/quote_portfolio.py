from __future__ import annotations

from decimal import Decimal


class QuotePortfolio:
    """Tracks state and risk metrics for all base assets sharing a single quote currency."""

    def __init__(self, exchange: str, quote_currency: str):
        self.exchange = exchange
        self.quote_currency = quote_currency
        self.total_cash: Decimal = Decimal("0")
        self.reserved_cash: Decimal = Decimal("0")
        self.open_orders: dict[str, Decimal] = {}
        self.asset_positions: dict[str, Decimal] = {}
        self.asset_mark_prices: dict[str, Decimal] = {}
        self.peak_equity: Decimal = Decimal("0")

    @property
    def available_cash(self) -> Decimal:
        return max(Decimal("0"), self.total_cash - self.reserved_cash)

    def update_cash(self, amount: Decimal) -> None:
        self.total_cash = max(Decimal("0"), Decimal(str(amount)))
        self._refresh_peak_equity()

    def update_asset_position(self, ticker_symbol: str, quantity: Decimal) -> None:
        self.asset_positions[ticker_symbol] = max(Decimal("0"), Decimal(str(quantity)))
        self._refresh_peak_equity()

    def update_asset_mark_price(self, ticker_symbol: str, price: Decimal) -> None:
        self.asset_mark_prices[ticker_symbol] = max(Decimal("0"), Decimal(str(price)))
        self._refresh_peak_equity()

    def reserve_cash(self, order_uuid: str, amount: Decimal) -> bool:
        amount_dec = Decimal(str(amount))
        if amount_dec <= Decimal("0"):
            return True
        if amount_dec > self.available_cash:
            return False
        self.reserved_cash += amount_dec
        self.open_orders[order_uuid] = amount_dec
        return True

    def release_cash(self, order_uuid: str) -> Decimal:
        if order_uuid not in self.open_orders:
            return Decimal("0")
        amount = self.open_orders.pop(order_uuid)
        self.reserved_cash = max(Decimal("0"), self.reserved_cash - amount)
        return amount

    def get_asset_notional(self, ticker_symbol: str) -> Decimal:
        qty = self.asset_positions.get(ticker_symbol, Decimal("0"))
        price = self.asset_mark_prices.get(ticker_symbol, Decimal("0"))
        return qty * price

    def get_total_holdings_notional(self) -> Decimal:
        return sum(
            (self.get_asset_notional(sym) for sym in self.asset_positions),
            Decimal("0"),
        )

    def get_total_equity(self) -> Decimal:
        return self.total_cash + self.get_total_holdings_notional()

    def _refresh_peak_equity(self) -> None:
        current_equity = self.get_total_equity()
        self.peak_equity = max(current_equity, self.peak_equity)

    def get_drawdown(self) -> Decimal:
        current_equity = self.get_total_equity()
        if self.peak_equity <= Decimal("0"):
            return Decimal("0")
        return (current_equity - self.peak_equity) / self.peak_equity

    def get_asset_concentration(self, ticker_symbol: str) -> Decimal:
        total_equity = self.get_total_equity()
        if total_equity <= Decimal("0"):
            return Decimal("0")
        notional = self.get_asset_notional(ticker_symbol)
        return notional / total_equity
