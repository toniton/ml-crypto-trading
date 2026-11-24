from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Sequence

from api.interfaces.backtest_request import BacktestDataSourceType
from api.interfaces.order import Order
from src.backtest.domain.result import BacktestFill, PortfolioSnapshot
from src.configuration.trading_config import TradingConfig
from src.core.interfaces.trading_journal import TradingJournal

if TYPE_CHECKING:
    from src.agent.backtest.backtest_service import BacktestService
    from src.vcs.application.service import VCSService

EPOCH_MS_THRESHOLD = 100_000_000_000
MAX_SIMULATED_EQUITY_POINTS = 500


def _snapshot_timestamp_to_iso(timestamp: int | float) -> str:
    seconds = timestamp / 1000.0 if timestamp >= EPOCH_MS_THRESHOLD else float(timestamp)
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()


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
    window_start: str | None = None
    window_end: str | None = None
    partial_fill_legs_merged: int = 0
    simulated_fees: Decimal = Decimal("0")
    live_fees: Decimal = Decimal("0")
    fee_drift: Decimal = Decimal("0")
    simulated_pnl: Decimal | None = None
    simulated_equity_curve: tuple[tuple[str, float], ...] = ()


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
            vcs_service: VCSService | None = None,
    ):
        self._backtest_service = backtest_service
        self._trading_journal = trading_journal
        self._price_tolerance_pct = price_tolerance_pct
        self._vcs_service = vcs_service

    def detect(self, ticker_symbol: str, commit_hash: str | None = None) -> DriftReport:
        request = self._backtest_service.build_request(
            ticker_symbol, source_type=BacktestDataSourceType.MARKET_DATA
        )
        trading_config = self._load_trading_config(commit_hash)
        if trading_config is not None:
            result = self._backtest_service.run(request, trading_config=trading_config)
        else:
            result = self._backtest_service.run(request)
        live_fills = self._trading_journal.entries(ticker_symbol)
        snapshots = (
            result.portfolio_snapshots
            if isinstance(getattr(result, "portfolio_snapshots", None), list)
            else []
        )
        raw_initial = getattr(result, "initial_balance", None)
        initial_balance = (
            Decimal(str(raw_initial))
            if isinstance(raw_initial, (Decimal, int, float))
            else None
        )
        return self._compare(
            ticker_symbol,
            result.fills,
            live_fills,
            portfolio_snapshots=snapshots,
            initial_balance=initial_balance,
        )

    def _load_trading_config(self, commit_hash: str | None) -> TradingConfig | None:
        if self._vcs_service is None:
            return None

        refs_to_try = [commit_hash.strip()] if commit_hash and commit_hash.strip() else ["refs/heads/main", "HEAD"]
        for ref in refs_to_try:
            try:
                raw_config = self._vcs_service.checkout(ref)
                return TradingConfig.model_validate(raw_config)
            except Exception:  # pylint: disable=broad-except
                if commit_hash and commit_hash.strip():
                    raise
        return None

    def _compare(  # pylint: disable=too-many-locals
            self,
            ticker_symbol: str,
            simulated_fills: list[BacktestFill],
            live_orders: list[Order],
            portfolio_snapshots: Sequence[PortfolioSnapshot] = (),
            initial_balance: Decimal | None = None,
    ) -> DriftReport:
        simulated_fill_count = len(simulated_fills)
        live_fill_count = len(live_orders)
        unique_parent_orders = {
            getattr(o, "parent_order_id", None) or o.uuid
            for o in live_orders
        }
        partial_legs = max(0, live_fill_count - len(unique_parent_orders))

        simulated_quantity = self._sum_fill_quantity(simulated_fills)
        live_quantity = self._sum_order_quantity(live_orders)

        simulated_average_price = self._average_fill_price(simulated_fills, simulated_quantity)
        live_average_price = self._average_order_price(live_orders, live_quantity)

        simulated_fees = sum((getattr(f, "fee", None) or Decimal("0") for f in simulated_fills), Decimal("0"))
        live_fees = sum((getattr(o, "fees", None) or Decimal("0") for o in live_orders), Decimal("0"))
        fee_drift = simulated_fees - live_fees

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

        simulated_equity_curve, simulated_pnl, window_start, window_end = (
            self._build_simulated_equity_curve(portfolio_snapshots, initial_balance)
        )

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
            window_start=window_start,
            window_end=window_end,
            partial_fill_legs_merged=partial_legs,
            simulated_fees=simulated_fees,
            live_fees=live_fees,
            fee_drift=fee_drift,
            simulated_pnl=simulated_pnl,
            simulated_equity_curve=simulated_equity_curve,
        )

    @staticmethod
    def _build_simulated_equity_curve(
            snapshots: Sequence[PortfolioSnapshot],
            initial_balance: Decimal | None,
    ) -> tuple[tuple[tuple[str, float], ...], Decimal | None, str | None, str | None]:
        if not snapshots:
            return (), None, None, None

        base_balance = (
            initial_balance
            if initial_balance is not None
            else Decimal(str(snapshots[0].equity))
        )

        if len(snapshots) <= MAX_SIMULATED_EQUITY_POINTS:
            selected = list(snapshots)
        else:
            step = len(snapshots) / MAX_SIMULATED_EQUITY_POINTS
            indices = {int(i * step) for i in range(MAX_SIMULATED_EQUITY_POINTS)}
            indices.add(0)
            indices.add(len(snapshots) - 1)
            selected = [snapshots[i] for i in sorted(indices) if i < len(snapshots)]

        curve = tuple(
            (
                _snapshot_timestamp_to_iso(snap.timestamp),
                round(float(Decimal(str(snap.equity)) - base_balance), 4),
            )
            for snap in selected
        )
        simulated_pnl = Decimal(str(snapshots[-1].equity)) - base_balance
        return curve, simulated_pnl, curve[0][0], curve[-1][0]

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
