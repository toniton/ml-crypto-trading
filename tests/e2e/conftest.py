from __future__ import annotations

import time
from decimal import Decimal
from queue import Queue

import pytest
import yaml

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import OrderStatus
from src.agent import AgentGateway
from src.agent.actions import (
    AgentActionExecutor,
    AgentActionService,
    AgentApprovalService,
)
from src.agent.automation import AutomationController, InvestigateActivityAnomaly
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.monitoring.starvation_watchdog import StarvationWatchdog
from src.configuration.llm_config import LlmConfig
from src.configuration.strategy_config import StrategyConfig, StrategyType
from src.configuration.strategies_config import StrategiesConfig
from src.core.interfaces.exchange_rest_builder import ExchangeRestBuilder
from src.core.interfaces.exchange_rest_service import ExchangeRestService
from src.core.interfaces.exchange_websocket_builder import ExchangeWebSocketBuilder
from src.core.interfaces.exchange_websocket_service import ExchangeWebSocketService
from src.core.interfaces.subscription_data import SubscriptionData
from src.events.message_event_bus import MessageEventBus
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.recorder.market_data_store import MarketDataStore
from src.server.app import ChatApp
from src.trading.activity.asset_activity_tracker import AssetActivityTracker
from src.trading.consensus.consensus_factor import ConsensusFactor
from src.trading.health.enums import TradingHealthState
from src.trading.live_trading_scheduler import LiveTradingScheduler
from src.trading.managers.manager_factory import ManagerFactory
from src.trading.sizing.position_sizer import PositionSizer
from src.trading.strategies.strategy_registry import StrategyRegistry
from src.trading.trading_executor import TradingExecutor
from src.vcs.application.service import VCSService
from tests.unit.agent.fakes import FakeLlmAdapter
from tests.unit.api_server.helpers import make_db_manager

VCS_SEED = """
assets:
  - name: "Bitcoin (Test)"
    base_ticker_symbol: "BTC"
    quote_ticker_symbol: "USD"
    exchange: "BACKTEST"
    min_quantity: 0.001
    quote_decimals: 2
    quantity_decimals: 3
    candles_timeframe: "MIN1"
    schedule: 1
    strategy: "TestBuy"
    consensus:
      buy: 0.5
      sell: 0.5
    enabled: true
"""

PROVIDER = ExchangeProvidersEnum.BACKTEST.value


class _FakeExchangeBuilder(ExchangeRestBuilder, ExchangeWebSocketBuilder):
    """Builder that only records the requested operation; executes return canned results."""

    def __init__(self):
        ExchangeRestBuilder.__init__(self)
        self.kind = None
        self.payload: dict = {}

    def market_data(self, ticker_symbol):
        self.kind, self.payload = "market_data", {"ticker_symbol": ticker_symbol}
        return self

    def candles(self, ticker_symbol, timeframe):
        self.kind, self.payload = "candles", {"ticker_symbol": ticker_symbol, "timeframe": timeframe}
        return self

    def account_balance(self):
        self.kind, self.payload = "account_balance", {}
        return self

    def account_fees(self):
        self.kind, self.payload = "account_fees", {}
        return self

    def instrument_fees(self, ticker_symbol):
        self.kind, self.payload = "instrument_fees", {"ticker_symbol": ticker_symbol}
        return self

    def order_update(self, instrument_name):
        self.kind, self.payload = "order_update", {"instrument": instrument_name}
        return self

    def create_order(self, uuid, ticker_symbol, quantity, price, trade_action, created_time=None):
        self.kind = "create_order"
        return self

    def get_order(self, uuid):
        self.kind, self.payload = "get_order", {"uuid": uuid}
        return self

    def get_open_orders(self, ticker_symbol=None):
        self.kind, self.payload = "get_open_orders", {"ticker_symbol": ticker_symbol}
        return self

    def cancel_order(self, uuid):
        self.kind, self.payload = "cancel_order", {"uuid": uuid}
        return self

    @property
    def key(self):
        return None

    def get_subscription_data(self) -> SubscriptionData:
        return SubscriptionData(payload=self.payload)

    def get_unsubscribe_payload(self, subscribe_payload: dict) -> dict:
        return {}

    def get_endpoint(self):
        return None

    def get_params(self) -> dict:
        return {}


class _FakeExchangeService(ExchangeRestService, ExchangeWebSocketService):
    """No-op exchange service implementing both REST and WebSocket contracts."""

    def __init__(self, provider: str = PROVIDER):
        self._provider = provider
        self._price: Decimal = Decimal("150")

    def set_price(self, price: Decimal) -> None:
        self._price = price

    def get_provider_name(self) -> str:
        return self._provider

    def get_websocket_url(self, visibility) -> str:
        return f"ws://localhost/fake/{self._provider}"

    def get_auth_request(self) -> dict:
        return {}

    def get_auth_handler(self):
        return None

    def get_heartbeat_handler(self):
        return None

    def builder(self) -> _FakeExchangeBuilder:
        return _FakeExchangeBuilder()

    def connect(self, callback) -> None:
        return None

    def subscribe(self, builder) -> None:
        return None

    def unsubscribe(self, builder) -> None:
        return None

    def execute(self, builder: _FakeExchangeBuilder):
        if builder.kind == "market_data":
            return MarketData(
                volume=Decimal("1000"),
                high_price=self._price,
                low_price=self._price - Decimal("1"),
                close_price=self._price,
                timestamp=time.time(),
            )
        if builder.kind == "candles":
            return []
        if builder.kind in ("account_fees", "instrument_fees"):
            return Fees(maker_fee_pct=Decimal("0.0"), taker_fee_pct=Decimal("0.0"))
        if builder.kind == "get_open_orders":
            return []
        return None


def build_test_asset() -> Asset:
    return Asset(
        base_ticker_symbol="BTC",
        quote_ticker_symbol="USD",
        quote_decimals=2,
        name="Bitcoin",
        exchange=ExchangeProvidersEnum.BACKTEST,
        min_quantity=0.001,
        quantity_decimals=3,
        schedule=AssetSchedule.EVERY_MINUTE,
        candles_timeframe=Timeframe.MIN1,
        strategies=[
            StrategyConfig(
                name="TestBuy",
                type=StrategyType.DYNAMIC,
                action="BUY",
                expression="close > 100",
            )
        ],
        consensus=ConsensusFactor(buy=0.5, sell=0.5),
        enabled=True,
    )


class E2EStack:
    """Deterministic in-process integration stack: simulated trading + agent automation + API."""

    def __init__(self, tmp_path):
        self.db = make_db_manager(str(tmp_path / "app.db"))
        self.vcs = VCSService(self.db)
        self.vcs.seed_if_empty(yaml.safe_load(VCS_SEED), author="test", message="seed")

        self.asset = build_test_asset()
        self.assets = [self.asset]

        self.trading_bus = MessageEventBus()
        self.agent_bus = MessageEventBus()

        self.container, self.journal = ManagerFactory.build_manager_container(
            self.db,
            self.assets,
            is_simulated=True,
            synchronous_execution=True,
            event_bus=self.trading_bus,
            config_vcs=self.vcs,
        )

        self.tracker = AssetActivityTracker()
        self.tracker.subscribe(self.trading_bus)

        self.exchange_service = _FakeExchangeService()
        self.container.rest_manager.register_service(self.exchange_service)
        self.container.websocket_manager.register_service(self.exchange_service)

        self.trading_executor = TradingExecutor(
            assets=self.assets,
            manager_container=self.container,
            activity_queue=Queue(),
            position_sizer=PositionSizer(global_formula=None, assets=self.assets),
            strategies_registry=StrategyRegistry(StrategiesConfig().strategies),
            event_bus=self.trading_bus,
        )
        self.trading_executor.init_application()

        self._build_automation()
        self._build_api()

    def _build_automation(self) -> None:
        config_service = ConfigurationService(vcs=self.vcs)
        self.action_service = AgentActionService(event_bus=self.agent_bus)
        self.approval_service = AgentApprovalService(
            vcs=self.vcs,
            configuration_service=config_service,
            action_service=self.action_service,
            event_bus=self.agent_bus,
        )
        self.agent_executor = AgentActionExecutor(
            action_service=self.action_service,
            approval_service=self.approval_service,
            vcs=self.vcs,
            configuration_service=config_service,
        )
        investigation = InvestigateActivityAnomaly(activity_provider=self.tracker)
        self.watchdog = StarvationWatchdog(
            activity_provider=self.tracker,
            assets=self.assets,
            event_bus=self.agent_bus,
            poll_interval_seconds=100000.0,
        )
        self.controller = AutomationController(
            event_bus=self.agent_bus,
            executor=self.agent_executor,
            approval_service=self.approval_service,
            investigation=investigation,
            watchdog=self.watchdog,
        )
        self.controller.start()

    def _build_api(self) -> None:
        from src.llm.llm_runtime_manager import LlmRuntimeManager
        from src.server.services.conversation_service import ConversationService
        from src.trading.local_trading_engine_proxy import LocalTradingEngineProxy
        from src.trading.trading_engine import TradingEngine

        self.trading_engine = TradingEngine(LiveTradingScheduler(), self.trading_executor)
        # Not start_application(): that would start the auto-scheduler. We drive
        # trading cycles deterministically in tests, so just open trading health.
        self.container.health_monitor.set_state(TradingHealthState.SYNCING)
        self.container.health_monitor.set_state(TradingHealthState.READY)
        self.container.health_monitor.set_state(TradingHealthState.TRADING)

        self.conversation_service = ConversationService(self.db)
        self.llm_manager = LlmRuntimeManager(LlmConfig(), self.db)
        self.trading_proxy = LocalTradingEngineProxy(
            trading_engine=self.trading_engine,
            market_data_store=MarketDataStore(),
            compare_backtest=self.agent_executor.compare_backtest_drift,
        )

        gateway = AgentGateway(FakeLlmAdapter([]), vcs=self.vcs)
        self.app = ChatApp.create(
            trading_proxy=self.trading_proxy,
            agent=gateway,
            event_bus=self.agent_bus,
            db_manager=self.db,
            vcs=self.vcs,
            llm_manager=self.llm_manager,
        )
        from fastapi.testclient import TestClient

        self.client = TestClient(self.app)
        self.projector = self.app.state.agent_event_projector

    def seed_market_data(self, close: Decimal = Decimal("150")) -> None:
        market_data = MarketData(
            volume=Decimal("1000"),
            high_price=close,
            low_price=close - Decimal("1"),
            close_price=close,
            timestamp=time.time(),
        )
        # pylint: disable=protected-access
        self.container.market_data_manager._update_market_data(self.asset.key, market_data)

    def complete_fill(self, order) -> None:
        """Simulate the exchange fill callback that marks an order COMPLETED."""
        order.status = OrderStatus.COMPLETED
        order.executed_time = float(time.time())
        order.fill_price = order.price
        # pylint: disable=protected-access
        self.container.order_manager._save_orders_to_database([order])

    def shutdown(self) -> None:
        self.controller.stop()
        self.projector.close()
        try:
            self.container.order_manager.shutdown()
            self.container.account_manager.shutdown()
        except Exception:  # pylint: disable=broad-except
            pass


@pytest.fixture
def e2e_stack(tmp_path):
    stack = E2EStack(tmp_path)
    yield stack
    stack.shutdown()


def wait_for(predicate, timeout: float = 8.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for condition (last={last!r})")
