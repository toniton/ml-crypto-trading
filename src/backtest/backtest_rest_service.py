from decimal import Decimal
from typing import Any, Optional
from uuid import uuid4

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order, OrderStatus
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from src.backtest.backtest_clock import BacktestClock
from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.backtest_rest_builder import BacktestRestBuilder
from src.backtest.data.backtest_data_set import BacktestDataSet
from src.backtest.execution.backtest_execution_engine import BacktestExecutionEngine
from src.core.interfaces.exchange_rest_service import ExchangeRestService
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum


class BacktestRestService(ApplicationLoggingMixin, ExchangeRestService):
    def __init__(
            self,
            clock: BacktestClock,
            event_bus: BacktestEventBus,
            datasets: dict[str, BacktestDataSet],
            execution_engine: BacktestExecutionEngine,
    ):
        self.clock = clock
        self.datasets = datasets
        self.bus = event_bus
        self.execution_engine = execution_engine
        self.account = execution_engine.account

    def get_provider_name(self) -> str:
        return ExchangeProvidersEnum.BACKTEST.value

    def builder(self) -> BacktestRestBuilder:
        return BacktestRestBuilder()

    def execute(self, builder: BacktestRestBuilder) -> Any:
        try:
            handler = getattr(self, f"_handle_{builder.method_name}")
        except AttributeError as exc:
            raise NotImplementedError(
                f"BacktestRestService does not support {builder.method_name}"
            ) from exc
        return handler(**builder.params)

    def _handle_market_data(self, ticker_symbol: str) -> MarketData:
        current = self.clock.now(ticker_symbol)
        dataset = self.datasets.get(ticker_symbol)
        data = dataset.get(current) if dataset else None
        if not data:
            raise ValueError(f"No market data for {ticker_symbol} at {current}")
        return MarketData(
            timestamp=data.timestamp,
            volume=data.volume,
            low_price=data.low_price,
            high_price=data.high_price,
            close_price=data.close_price,
        )

    def _handle_account_balance(self) -> list[AccountBalance]:
        return self.execution_engine.get_balances_snapshot()

    def _handle_account_fees(self, provider_name: str = None) -> Fees:  # pylint: disable=unused-argument
        return Fees(
            maker_fee_pct=Decimal("0.0"),
            taker_fee_pct=Decimal("0.0"),
        )

    def _handle_instrument_fees(self, ticker_symbol: str, provider_name: str = None) -> Fees:  # pylint: disable=unused-argument
        return Fees(
            maker_fee_pct=Decimal("0.0"),
            taker_fee_pct=Decimal("0.0"),
        )

    def _handle_create_order(
            self,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: str,
            trade_action: TradeAction,
            created_time: Optional[float] = None,
    ) -> Order:
        executed_at = created_time if created_time is not None else self.clock.now(ticker_symbol)
        order = Order(
            uuid=uuid or str(uuid4()),
            ticker_symbol=ticker_symbol,
            quantity=quantity,
            price=Decimal(price),
            status=OrderStatus.PENDING,
            provider_name=self.get_provider_name(),
            trade_action=trade_action,
            created_time=executed_at,
        )
        self.account.orders.append(order)
        self.execution_engine.submit(order, ticker_symbol)

        self.app_logger.info(
            f"Order submitted: {trade_action.name} {quantity} {ticker_symbol} "
            f"@ {price} (pending execution)"
        )
        return order

    def _handle_get_order(self, uuid: str) -> Order:
        for order in self.account.orders:
            if order.uuid == uuid:
                return order
        raise RuntimeWarning(f"Order {uuid} not found")

    def _handle_get_open_orders(self, ticker_symbol: str = None) -> list[Order]:
        return self.execution_engine.get_pending_orders(ticker_symbol)

    def _handle_cancel_order(self, uuid: str) -> None:
        for order in self.account.orders:
            if order.uuid == uuid and order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED

    def _handle_candles(self, ticker_symbol: str, timeframe: Timeframe) -> list[Candle]:  # pylint: disable=unused-argument
        market_data = self._handle_market_data(ticker_symbol)
        return [
            Candle(
                open=market_data.close_price,
                high=market_data.high_price,
                low=market_data.low_price,
                close=market_data.close_price,
                start_time=float(market_data.timestamp),
            )
        ]
