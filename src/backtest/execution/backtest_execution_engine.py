from decimal import Decimal
from typing import Optional

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.backtest.backtest_clock import BacktestClock
from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.data.backtest_data_set import BacktestDataSet
from src.backtest.events.domain_events import (
    OrderFilledEvent,
    OrderCancelledEvent,
    OrderSubmittedEvent,
    BalanceUpdateEvent,
)
from src.backtest.execution.execution_types import PendingOrder, ExecutionResult
from src.backtest.execution.execution_model import ExecutionModel
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class SimulatedAccount:
    def __init__(self, initial_balance: Decimal = Decimal("10000.0")):
        self.balance_usd: Decimal = initial_balance
        self.positions: dict[str, Decimal] = {}
        self.orders: list[Order] = []


class BacktestExecutionEngine(ApplicationLoggingMixin):
    def __init__(
            self,
            clock: BacktestClock,
            datasets: dict[str, BacktestDataSet],
            bus: BacktestEventBus,
            execution_model: ExecutionModel,
            assets: dict[str, Asset],
            initial_balance: Decimal = Decimal("10000.0"),
    ):
        self._clock = clock
        self._datasets = datasets
        self._bus = bus
        self._model = execution_model
        self._assets = assets
        self.account = SimulatedAccount(initial_balance)
        self._pending: dict[str, list[PendingOrder]] = {}
        self._results: list[ExecutionResult] = []

    def submit(self, order: Order, ticker_symbol: str) -> None:
        latency = self._model.latency.get_latency(order, ticker_symbol)
        eligible_at = order.created_time + latency

        execution_timestamp = self._clock.next_timestamp_at_or_after(
            ticker_symbol, eligible_at
        )

        pending = PendingOrder(
            order_uuid=order.uuid,
            ticker_symbol=ticker_symbol,
            trade_action=order.trade_action,
            quantity=Decimal(order.quantity),
            requested_price=order.price,
            signal_at=order.created_time,
            submitted_at=order.created_time,
            eligible_at=eligible_at,
            execution_timestamp=execution_timestamp,
        )

        self._pending.setdefault(ticker_symbol, []).append(pending)

        if not self._find_order(order.uuid):
            self.account.orders.append(order)

        self._bus.publish(OrderSubmittedEvent(order=order))

        self.app_logger.debug(
            f"Order submitted: {order.uuid} {ticker_symbol} "
            f"eligible_at={eligible_at} execution_timestamp={execution_timestamp}"
        )

    def process(self, ticker_symbol: str, current_timestamp: float) -> None:
        pending_list = self._pending.get(ticker_symbol, [])
        due = [
            pending for pending in pending_list
            if pending.execution_timestamp is not None and pending.execution_timestamp <= current_timestamp
        ]
        self._pending[ticker_symbol] = [
            pending for pending in pending_list
            if pending.execution_timestamp is None or pending.execution_timestamp > current_timestamp
        ]

        for pending in due:
            self._fill_order(pending)

    def _fill_order(self, pending: PendingOrder) -> None:
        dataset = self._datasets.get(pending.ticker_symbol)
        data = dataset.get(pending.execution_timestamp) if dataset else None
        if not data:
            self._cancel_order(pending, "no_market_data_at_tick")
            return

        market_price = data.close_price

        asset = self._assets.get(pending.ticker_symbol)
        if not asset:
            self._cancel_order(pending, "unknown_asset")
            return

        executed_price = self._model.slippage.apply(
            pending.trade_action, market_price, asset
        )

        notional = pending.quantity * executed_price
        fee = self._model.fees.calculate(notional)

        if not self._apply_to_account(pending, executed_price, fee):
            self._cancel_order(pending, "insufficient_funds_at_fill")
            return

        order = self._find_order(pending.order_uuid)
        if order:
            order.status = OrderStatus.COMPLETED
            order.executed_time = float(pending.execution_timestamp)
            order.fee = fee

        slippage_per_unit = executed_price - market_price
        slippage_cost = slippage_per_unit * pending.quantity

        result = ExecutionResult(
            order_uuid=pending.order_uuid,
            ticker_symbol=pending.ticker_symbol,
            trade_action=pending.trade_action,
            status=OrderStatus.COMPLETED,
            requested_price=pending.requested_price,
            market_price=market_price,
            execution_price=executed_price,
            requested_quantity=pending.quantity,
            executed_quantity=pending.quantity,
            slippage_per_unit=slippage_per_unit,
            slippage_cost=slippage_cost,
            fee=fee,
            signal_at=pending.signal_at,
            submitted_at=pending.submitted_at,
            eligible_at=pending.eligible_at,
            executed_at=float(pending.execution_timestamp),
        )
        self._results.append(result)

        if order:
            self._bus.publish(OrderFilledEvent(order=order, execution=result))
        balances = self.get_balances_snapshot()
        self._bus.publish(BalanceUpdateEvent(balances=balances))

        self.app_logger.info(
            f"Fill: {pending.trade_action.name} {pending.quantity} "
            f"{pending.ticker_symbol} @ {executed_price:f} "
            f"(market={market_price:f}, slippage={slippage_per_unit:f}, fee={fee:f})"
        )

    def _apply_to_account(self, pending: PendingOrder, price: Decimal, fee: Decimal) -> bool:
        total = pending.quantity * price

        if pending.trade_action == TradeAction.BUY:
            cost = total + fee
            if self.account.balance_usd < cost:
                return False
            self.account.balance_usd -= cost
            self.account.positions[pending.ticker_symbol] = (
                    self.account.positions.get(pending.ticker_symbol, Decimal("0"))
                    + pending.quantity
            )
        else:
            position = self.account.positions.get(pending.ticker_symbol, Decimal("0"))
            if position < pending.quantity:
                return False
            self.account.positions[pending.ticker_symbol] -= pending.quantity
            self.account.balance_usd += total - fee

        return True

    def _cancel_order(self, pending: PendingOrder, reason: str) -> None:
        order = self._find_order(pending.order_uuid)
        if order:
            order.status = OrderStatus.CANCELLED
        self._bus.publish(OrderCancelledEvent(
            order=order or self._make_cancelled_order(pending)
        ))
        self.app_logger.warning(
            f"Order cancelled: {pending.order_uuid} {pending.ticker_symbol} "
            f"reason={reason}"
        )

    def _find_order(self, uuid: str) -> Optional[Order]:
        for order in self.account.orders:
            if order.uuid == uuid:
                return order
        return None

    def _make_cancelled_order(self, pending: PendingOrder) -> Order:
        return Order(
            uuid=pending.order_uuid,
            provider_name=ExchangeProvidersEnum.BACKTEST.value,
            ticker_symbol=pending.ticker_symbol,
            price=pending.requested_price,
            quantity=str(pending.quantity),
            trade_action=pending.trade_action,
            created_time=pending.signal_at,
            status=OrderStatus.CANCELLED,
        )

    def get_balances_snapshot(self) -> list[AccountBalance]:
        balances = [
            AccountBalance(currency="USD", available_balance=self.account.balance_usd)
        ]
        for ticker, qty in self.account.positions.items():
            base = ticker.split("_")[0]
            balances.append(AccountBalance(currency=base, available_balance=qty))
        return balances

    def get_pending_orders(self, ticker_symbol: str = None) -> list[Order]:
        orders = []
        for symbol, pending_list in self._pending.items():
            if ticker_symbol and symbol != ticker_symbol:
                continue
            for pending in pending_list:
                orders.append(Order(
                    uuid=pending.order_uuid,
                    provider_name=ExchangeProvidersEnum.BACKTEST.value,
                    ticker_symbol=pending.ticker_symbol,
                    price=pending.requested_price,
                    quantity=str(pending.quantity),
                    trade_action=pending.trade_action,
                    created_time=pending.signal_at,
                    status=OrderStatus.PENDING,
                ))
        return orders

    @property
    def results(self) -> list[ExecutionResult]:
        return list(self._results)
