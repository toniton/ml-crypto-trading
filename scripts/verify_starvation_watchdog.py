#!/usr/bin/env python3
"""Manual end-to-end verification of the Autonomous Starvation Watchdog.

Runs the full agent-automation stack in-memory (no DB, no live exchange):

    tracker -> watchdog -> event bus -> AutomationController -> investigation
        -> executor -> projector -> conversation store

and prints the agent's autonomous reactions:

1. When an asset goes silent, the watchdog emits a TradingActivityAnomalyDetectedEvent.
2. The automation controller investigates and posts a Drift Diagnostic chat message.
3. For a risk/config-gating anomaly (signals but no orders) it raises an approval
   proposal to pause the asset.

Usage:
    ./venv/bin/python3 scripts/verify_starvation_watchdog.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from decimal import Decimal
from typing import List, Optional
from unittest.mock import MagicMock

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
from src.agent.monitoring.starvation_watchdog import StarvationWatchdog
from src.core.interfaces.conversation_store import (
    ConversationMessage,
    ConversationStore,
    SessionSummary,
)
from src.events.agent_events import TradingActivityAnomalyDetectedEvent
from src.events.message_event_bus import MessageEventBus
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.server.agent_event_projector import AgentEventProjector
from src.trading.activity.asset_activity_tracker import AssetActivityTracker
from src.trading.events import MarketDataEvent


class PrintingConversationStore(ConversationStore):
    """In-memory store that prints every message the agent posts to the chat."""

    def __init__(self):
        self._sessions: dict[str, List[ConversationMessage]] = {}

    def get_or_create(self, session_id: Optional[str]) -> str:
        resolved = session_id or "demo"
        self._sessions.setdefault(resolved, [])
        return resolved

    def history(self, session_id: str):
        return []

    def append(self, session_id: str, message: ConversationMessage) -> None:
        self._sessions.setdefault(session_id, []).append(message)
        blocks = (message.payload or {}).get("blocks") or []
        block_types = [b.get("type") for b in blocks if isinstance(b, dict)]
        print(f"    [agent -> chat] {message.content}")
        if block_types:
            print(f"                    blocks={block_types}")

    def messages(self, session_id: str) -> List[ConversationMessage]:
        return list(self._sessions.get(session_id, []))

    def get_message(self, message_id: str) -> Optional[ConversationMessage]:
        for messages in self._sessions.values():
            for message in reversed(messages):
                if message.message_id == message_id:
                    return message
        return None

    def list_sessions(self) -> List[SessionSummary]:
        now = time.time()
        return [
            SessionSummary(id=sid, created_at=now, updated_at=now, message_count=len(msgs))
            for sid, msgs in self._sessions.items()
        ]


def asset() -> Asset:
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


def wait_for(predicate, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise RuntimeError("Timed out waiting for the autonomous agent reaction")


def main() -> None:
    print("=" * 72)
    print("Verifying the Autonomous Starvation Watchdog")
    print("=" * 72)

    bus = MessageEventBus()
    tracker = AssetActivityTracker()
    tracker.subscribe(bus)

    # VCS/config are mocked: enough to exercise the proposal/approval path.
    vcs = MagicMock()
    vcs.head.return_value = MagicMock(hash="deadbeef" * 5)
    configuration_service = MagicMock()
    configuration_service.load_raw_config.return_value = {}
    action_service = AgentActionService(event_bus=bus)
    approval_service = AgentApprovalService(
        vcs=vcs,
        configuration_service=configuration_service,
        action_service=action_service,
        event_bus=bus,
    )
    executor = AgentActionExecutor(
        action_service=action_service,
        approval_service=approval_service,
        vcs=vcs,
        configuration_service=configuration_service,
    )

    investigation = InvestigateActivityAnomaly(activity_provider=tracker)
    watchdog = StarvationWatchdog(
        activity_provider=tracker,
        assets=[asset()],
        event_bus=bus,
        poll_interval_seconds=100000.0,  # we drive detection manually below
    )
    controller = AutomationController(
        event_bus=bus,
        executor=executor,
        approval_service=approval_service,
        investigation=investigation,
        watchdog=watchdog,
    )
    controller.start()

    store = PrintingConversationStore()
    projector = AgentEventProjector(event_bus=bus, conversation_store=store)
    projector.subscribe()

    try:
        print("\n[1] BTC_USD market data feed goes silent (no activity for hours) ...")
        bus.publish(MarketDataEvent(
            ticker_symbol="BTC_USD",
            market_data=MarketData(
                volume=Decimal("1"), high_price=Decimal("2"),
                low_price=Decimal("1"), close_price=Decimal("1.5"),
                timestamp=time.time() - 10000.0,
            ),
        ))

        print("\n[2] Starvation watchdog poll detects the anomaly ...")
        emitted = watchdog.run_once()
        assert len(emitted) == 1, "expected one anomaly event"
        event = emitted[0]
        print(f"    TradingActivityAnomalyDetectedEvent asset={event.asset} kind={event.anomaly_kind}")

        print("\n[3] Agent autonomously investigates and posts a Drift Diagnostic ...")
        wait_for(lambda: any("Anomaly kind" in m.content for m in _all_messages(store)))

        print("\n[4] Risk/config-gating anomaly (signals, but no orders) -> approval proposal ...")
        bus.publish(TradingActivityAnomalyDetectedEvent(
            asset="BTC_USD",
            anomaly_kind="NO_ORDERS",
            threshold=240.0,
            detected_at=str(time.time()),
        ))
        wait_for(lambda: projector.list_approvals())
        approval = projector.list_approvals()[0]
        change = approval["proposed_change"]["changes"][0]
        print(f"    Approval requested: {approval['title']}")
        print(f"      {change['path']}: {change['old_value']} -> {change['new_value']}")
        print(f"      reason: {change['reason']}")

        print("\n[5] Approval card projected into the chat conversation ...")
        wait_for(lambda: any(
            (m.payload or {}).get("blocks", [{}])[0].get("type") == "agent_approval"
            for m in _all_messages(store)
        ))
        print("    agent_approval block visible in conversation store (and streamed over WS).")

        print("\n" + "=" * 72)
        print("SUCCESS: watchdog detected starvation and the agent reacted autonomously.")
        print("=" * 72)
    finally:
        controller.stop()
        projector.close()


def _all_messages(store: PrintingConversationStore):
    return [m for s in store.list_sessions() for m in store.messages(s.id)]


if __name__ == "__main__":
    main()