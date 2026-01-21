import threading
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Any
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
from backtest.backtest_rest_builder import BacktestRestBuilder
from backtest.events.domain_events import BalanceUpdateEvent, OrderFillEvent
from src.configuration.application_config import ApplicationConfig
from src.core.managers.exchange_rest_manager import ExchangeProvidersEnum
from src.core.interfaces.exchange_rest_service import ExchangeRestService
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin


@dataclass
class SimulatedAccount:
    balance_usd: Decimal = Decimal("10000.0")
    positions: Dict[str, Decimal] = field(default_factory=dict)
    orders: List[Order] = field(default_factory=list)


class BacktestRestService(ApplicationLoggingMixin, ExchangeRestService):
    def __init__(
            self,
            clock: BacktestClock,
            event_bus: BacktestEventBus,
            data_loader: BacktestDataLoader,
            config: ApplicationConfig = None
    ):
        self.clock = clock
        self.loader = data_loader
        self.bus = event_bus
        self.account = SimulatedAccount(
            balance_usd=config.backtest_initial_balance if config else Decimal("10000.0")
        )
        self._lock = threading.Lock()

    def get_provider_name(self) -> str:
        return ExchangeProvidersEnum.CRYPTO_DOT_COM.name

    def builder(self) -> BacktestRestBuilder:
        return BacktestRestBuilder()

    def execute(self, builder: BacktestRestBuilder) -> Any:
        method = getattr(self, f"_handle_{builder.method_name}", None)
        if not method or not callable(method):
            raise NotImplementedError(f"BacktestRestService does not support {builder.method_name}")
        return method(**builder.params)  # pylint: disable=not-callable

    def _handle_market_data(self, ticker_symbol: str) -> MarketData:
        current = self.clock.now(ticker_symbol)
        data = self.loader.get_data(ticker_symbol, current)
        if not data:
            raise ValueError(f"No market data for {ticker_symbol} at {current}")
        return MarketData(
            timestamp=data.timestamp,
            volume=str(data.volume),
            low_price=str(data.low_price),
            high_price=str(data.high_price),
            close_price=str(data.close_price)
        )

    def _handle_account_balance(self) -> list[AccountBalance]:
        with self._lock:
            balances = [
                AccountBalance(
                    currency="USD",
                    available_balance=self.account.balance_usd,
                )
            ]
            for ticker, qty in self.account.positions.items():
                # Ticker is usually BASE_QUOTE, we need BASE
                base_currency = ticker.split("_")[0]
                balances.append(
                    AccountBalance(
                        currency=base_currency,
                        available_balance=qty
                    )
                )
            return balances

    def _handle_account_fees(self) -> Fees:
        return Fees(
            maker_fee_pct=Decimal("0.0"),
            taker_fee_pct=Decimal("0.0")
        )

    def _handle_instrument_fees(self, _ticker_symbol: str) -> Fees:
        return Fees(
            maker_fee_pct=Decimal("0.0"),
            taker_fee_pct=Decimal("0.0")
        )

    def _handle_create_order(
            self,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: str,
            trade_action: TradeAction
    ) -> None:
        order_uuid = uuid or str(uuid4())
        qty = Decimal(quantity)
        p = Decimal(price)
        total_value = qty * p

        if trade_action == TradeAction.BUY:
            with self._lock:
                if self.account.balance_usd < total_value:
                    raise ValueError(
                        f"Insufficient balance: {self.account.balance_usd} < {total_value}"
                    )
                self.account.balance_usd -= total_value
                self.account.positions[ticker_symbol] = (
                        self.account.positions.get(ticker_symbol, Decimal("0")) + qty
                )
        else:
            with self._lock:
                current_position = self.account.positions.get(ticker_symbol, Decimal("0"))
                if current_position < qty:
                    raise ValueError(
                        f"Insufficient position: {current_position} < {qty}"
                    )
                self.account.positions[ticker_symbol] -= qty
                self.account.balance_usd += total_value

        with self._lock:
            order = Order(
                uuid=order_uuid,
                ticker_symbol=ticker_symbol,
                quantity=quantity,
                price=p,
                status=OrderStatus.COMPLETED,
                provider_name=self.get_provider_name(),
                trade_action=trade_action,
                created_time=self.clock.now(ticker_symbol)
            )
            self.account.orders.append(order)

        self.app_logger.info(
            f"BacktestRestService: {trade_action.name} {quantity} {ticker_symbol} @ {price} "
            f"(Balance: ${self.account.balance_usd})"
        )

        self.bus.publish(OrderFillEvent(order=order))
        balances = self._handle_account_balance()
        self.bus.publish(BalanceUpdateEvent(balances=balances))

    def _handle_get_order(self, uuid: str) -> Order:
        try:
            return next(o for o in self.account.orders if o.uuid == uuid)
        except StopIteration as exc:
            raise RuntimeWarning(f"Order {uuid} not found") from exc

    def _handle_cancel_order(self, uuid: str) -> None:
        self.account.orders = [o for o in self.account.orders if o.uuid != uuid]

    def _handle_candles(self, ticker_symbol: str, _timeframe: Timeframe) -> list[Candle]:
        market_data = self._handle_market_data(ticker_symbol)
        return [
            Candle(
                open=market_data.close_price,
                high=market_data.high_price,
                low=market_data.low_price,
                close=market_data.close_price,
                start_time=float(market_data.timestamp)
            )
        ]
