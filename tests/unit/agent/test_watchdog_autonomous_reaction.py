from __future__ import annotations

import time
from decimal import Decimal
from typing import Callable

import pytest
import yaml

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.market_data import MarketData
from api.interfaces.timeframe import Timeframe
from src.agent.actions import (
    AgentActionExecutor,
    AgentActionService,
    AgentApprovalService,
)
from src.agent.automation import AutomationController, InvestigateActivityAnomaly
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.monitoring.starvation_watchdog import StarvationWatchdog
from src.events.agent_events import TradingActivityAnomalyDetectedEvent
from src.events.message_event_bus import MessageEventBus
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.server.agent_event_projector import AgentEventProjector
from src.trading.activity.asset_activity_tracker import AssetActivityTracker
from src.trading.events import MarketDataEvent
from src.vcs.application.service import VCSService
from tests.unit.agent.fakes import FakeConversationStore
from tests.unit.api_server.helpers import make_db_manager

SAMPLE_CONFIG = """
assets:
  - name: "Bitcoin (Crypto.com)"
    base_ticker_symbol: "BTC"
    quote_ticker_symbol: "USD"
    exchange: "CRYPTO_DOT_COM"
    min_quantity: 0.00005
    quote_decimals: 2
    quantity_decimals: 5
    candles_timeframe: "MIN1"
    schedule: 1
    consensus:
      buy: 1.3
      sell: 0.5
dynamic_quantity: "max(min_qty, eq * 0.1)"
"""


def _asset() -> Asset:
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
        enabled=True,
    )


def wait_for(predicate: Callable, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for autonomous agent reaction")


@pytest.fixture
def system(tmp_path):
    db_mgr = make_db_manager(str(tmp_path / "app.db"))
    vcs = VCSService(db_mgr)
    vcs.seed_if_empty(yaml.safe_load(SAMPLE_CONFIG), author="test", message="seed")

    bus = MessageEventBus()
    tracker = AssetActivityTracker()
    tracker.subscribe(bus)

    action_service = AgentActionService(event_bus=bus)
    config_service = ConfigurationService(vcs=vcs)
    approval_service = AgentApprovalService(
        vcs=vcs,
        configuration_service=config_service,
        action_service=action_service,
        event_bus=bus,
    )
    executor = AgentActionExecutor(
        action_service=action_service,
        approval_service=approval_service,
        vcs=vcs,
        configuration_service=config_service,
    )

    investigation = InvestigateActivityAnomaly(activity_provider=tracker)
    watchdog = StarvationWatchdog(
        activity_provider=tracker,
        assets=[_asset()],
        event_bus=bus,
        poll_interval_seconds=100000.0,
    )
    controller = AutomationController(
        event_bus=bus,
        executor=executor,
        approval_service=approval_service,
        investigation=investigation,
        watchdog=watchdog,
    )
    controller.start()

    store = FakeConversationStore()
    projector = AgentEventProjector(event_bus=bus, conversation_store=store)
    projector.subscribe()

    yield {
        "bus": bus,
        "tracker": tracker,
        "watchdog": watchdog,
        "controller": controller,
        "store": store,
        "projector": projector,
    }

    controller.stop()
    projector.close()


def _stale_market_data_event(ticker: str) -> MarketDataEvent:
    return MarketDataEvent(
        ticker_symbol=ticker,
        market_data=MarketData(
            volume=Decimal("1"),
            high_price=Decimal("2"),
            low_price=Decimal("1"),
            close_price=Decimal("1.5"),
            timestamp=time.time() - 10000.0,
        ),
    )


def test_watchdog_detects_starvation_and_agent_posts_diagnostic(system):
    bus = system["bus"]
    store = system["store"]
    # Simulate an asset whose market data feed has been silent well beyond the threshold.
    bus.publish(_stale_market_data_event("BTC_USD"))

    emitted = system["watchdog"].run_once()
    assert len(emitted) == 1
    assert emitted[0].asset == "BTC_USD"
    assert emitted[0].anomaly_kind == "NO_MARKET_DATA"

    def diagnostic_landed():
        for session in store.list_sessions():
            for message in store.messages(session.id):
                if "BTC_USD" in message.content and "Anomaly kind" in message.content:
                    return message
        return None

    message = wait_for(diagnostic_landed)
    assert "NO_MARKET_DATA" in message.content
    assert "Connectivity" in message.content


def test_watchdog_agent_proposes_pause_for_config_gating(system):
    bus = system["bus"]
    store = system["store"]
    projector = system["projector"]

    # Directly emit a NO_ORDERS anomaly (signals present but no orders -> risk/config gating).
    event = TradingActivityAnomalyDetectedEvent(
        asset="BTC_USD",
        anomaly_kind="NO_ORDERS",
        threshold=240.0,
        detected_at=str(time.time()),
    )
    bus.publish(event)

    def approval_requested():
        approvals = projector.list_approvals()
        return approvals[0] if approvals else None

    approval = wait_for(approval_requested)
    assert approval["status"] == "PENDING"
    assert approval["asset"] == "BTC_USD"
    proposed = approval["proposed_change"]["changes"][0]
    assert proposed["path"] == "assets.BTC_USD.enabled"
    assert proposed["new_value"] is False

    def card_landed():
        for session in store.list_sessions():
            for message in store.messages(session.id):
                blocks = (message.payload or {}).get("blocks") or []
                if blocks and blocks[0].get("type") == "agent_approval":
                    return message
        return None

    message = wait_for(card_landed)
    assert message.payload["blocks"][0]["approval_id"] == approval["id"]