from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from api.interfaces.backtest_request import BacktestDataSourceType
from api.interfaces.order import Order
from src.agent.backtest.backtest_service import BacktestService
from src.backtest.domain.result import BacktestFill
from src.core.interfaces.trading_journal import TradingJournal


@dataclass(frozen=True)
class DriftReport:
    """Comparison between a backtest replay and actual live trading."""

    ticker_symbol: str
    simulated_fill_count: int
    live_fill_count: int
    simulated_quantity: Decimal
    live_quantity: Decimal
    simulated_average_price: Decimal | None
    live_average_price: Decimal | None
    fill_count_drift: int
    quantity_drift: Decimal
    price_drift: Decimal | None
    drifted: bool


class BacktestDriftDetector:
    """Detects drift between a backtest replay and actual live trading.

    Replays the recorded live market data through the backtest engine and
    compares the simulated fills against the fills recorded live by the trading
    journal. Divergence indicates drift in the execution model, latency, or
    data.
    """

    def __init__(
            self,
            backtest_service: BacktestService,
            trading_journal: TradingJournal,
            price_tolerance_pct: Decimal = Decimal("0.5"),
    ):
        self._backtest_service = backtest_service
        self._trading_journal = trading_journal
        self._price_tolerance_pct = price_tolerance_pct

    def detect(self, ticker_symbol: str) -> DriftReport:
        request = self._backtest_service.build_request(
            ticker_symbol, source_type=BacktestDataSourceType.MARKET_DATA
        )
        result = self._backtest_service.run(request)
        live_fills = self._trading_journal.entries(ticker_symbol)
        return self._compare(ticker_symbol, result.fills, live_fills)

    def _compare(
            self,
            ticker_symbol: str,
            simulated_fills: list[BacktestFill],
            live_orders: list[Order],
    ) -> DriftReport:
        simulated_fill_count = len(simulated_fills)
        live_fill_count = len(live_orders)

        simulated_quantity = self._sum_fill_quantity(simulated_fills)
        live_quantity = self._sum_order_quantity(live_orders)

        simulated_average_price = self._average_fill_price(simulated_fills, simulated_quantity)
        live_average_price = self._average_order_price(live_orders, live_quantity)

        fill_count_drift = simulated_fill_count - live_fill_count
        quantity_drift = simulated_quantity - live_quantity
        price_drift = (
            simulated_average_price - live_average_price
            if simulated_average_price is not None and live_average_price is not None
            else None
        )

        drifted = fill_count_drift != 0 or quantity_drift != 0
        if price_drift is not None and live_average_price:
            price_drift_pct = abs(price_drift) / live_average_price * Decimal("100")
            drifted = drifted or price_drift_pct > self._price_tolerance_pct

        return DriftReport(
            ticker_symbol=ticker_symbol,
            simulated_fill_count=simulated_fill_count,
            live_fill_count=live_fill_count,
            simulated_quantity=simulated_quantity,
            live_quantity=live_quantity,
            simulated_average_price=simulated_average_price,
            live_average_price=live_average_price,
            fill_count_drift=fill_count_drift,
            quantity_drift=quantity_drift,
            price_drift=price_drift,
            drifted=drifted,
        )

    @staticmethod
    def _sum_fill_quantity(fills: list[BacktestFill]) -> Decimal:
        return sum((fill.quantity for fill in fills), Decimal("0"))

    @staticmethod
    def _sum_order_quantity(orders: list[Order]) -> Decimal:
        return sum((Decimal(order.quantity) for order in orders), Decimal("0"))

    @staticmethod
    def _average_fill_price(fills: list[BacktestFill], quantity: Decimal) -> Decimal | None:
        if not quantity:
            return None
        notional = sum((fill.execution_price * fill.quantity for fill in fills), Decimal("0"))
        return notional / quantity

    @staticmethod
    def _average_order_price(orders: list[Order], quantity: Decimal) -> Decimal | None:
        if not quantity:
            return None
        notional = sum(
            (BacktestDriftDetector._fill_price(order) * Decimal(order.quantity) for order in orders),
            Decimal("0"),
        )
        return notional / quantity

    @staticmethod
    def _fill_price(order: Order) -> Decimal:
        return order.fill_price if order.fill_price is not None else order.price
