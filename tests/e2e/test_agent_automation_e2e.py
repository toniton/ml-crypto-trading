from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal

from api.interfaces.market_data import MarketData
from src.events.agent_events import TradingActivityAnomalyDetectedEvent
from src.events.message_event_bus import CallbackSubscription
from src.trading.events import MarketDataEvent

from .conftest import wait_for


def _stale_market_data(ticker: str = "BTC_USD") -> MarketDataEvent:
    return MarketDataEvent(
        ticker_symbol=ticker,
        market_data=MarketData(
            volume=Decimal("1000"),
            high_price=Decimal("150"),
            low_price=Decimal("149"),
            close_price=Decimal("150"),
            timestamp=time.time() - 10000.0,
        ),
    )


def test_starvation_watchdog_detects_and_records_reaction(e2e_stack):
    stack = e2e_stack

    # Asset goes silent (stale market data registered before the watchdog poll).
    stack.trading_bus.publish(_stale_market_data())

    emitted = stack.watchdog.run_once()
    assert len(emitted) == 1
    assert emitted[0].asset == "BTC_USD"
    assert emitted[0].anomaly_kind == "NO_MARKET_DATA"

    def timeline_recorded():
        res = stack.client.get("/api/v1/timeline?entity_id=BTC_USD&category=AGENT")
        items = res.json()
        return next(
            (i for i in items if "Trading Starvation Detected" in i.get("title", "")),
            None,
        )

    item = wait_for(timeline_recorded)
    assert item["entity" if "entity" in item else "primary_entity"].get("id") == "BTC_USD"
    assert "NO_MARKET_DATA" in item["summary"]

    # Current behaviour: autonomous chat messages are suppressed; only the timeline
    # decision is recorded. No STARVATION SEND_MESSAGE action may be auto-created.
    time.sleep(0.5)
    actions = stack.projector.list_actions()
    starvation_messages = [
        a for a in actions if a.get("reason", {}).get("trigger") == "STARVATION_DETECTED"
    ]
    assert starvation_messages == []


def test_agent_proposes_and_user_approves_e2e(e2e_stack):
    stack = e2e_stack
    resolved = []

    def on_resolved(event):
        resolved.append(event)

    stack.agent_bus.subscribe("AgentApprovalResolvedEvent", CallbackSubscription(on_resolved))

    stack.agent_bus.publish(
        TradingActivityAnomalyDetectedEvent(
            asset="BTC_USD",
            anomaly_kind="NO_ORDERS",
            threshold=240.0,
            detected_at=str(datetime.now(timezone.utc)),
        )
    )

    def approval_pending():
        approvals = stack.projector.list_approvals()
        return approvals[0] if approvals else None

    approval = wait_for(approval_pending)
    approval_id = approval["id"]
    assert approval["status"] == "PENDING"
    assert approval["asset"] == "BTC_USD"
    change = approval["proposed_change"]["changes"][0]
    assert change["path"] == "assets.BTC_USD.enabled"
    assert change["new_value"] is False

    # Approval card is materialized into a system conversation (single source of truth).
    def card_landed():
        for session in stack.conversation_service.list_sessions():
            for m in stack.conversation_service.messages(session.id):
                blocks = (m.payload or {}).get("blocks") or []
                if blocks and blocks[0].get("type") == "agent_approval":
                    return m
        return None

    assert wait_for(card_landed) is not None

    # User approves via the async endpoint (202); resolution streams as an event.
    res = stack.client.post(
        f"/api/v1/agent/approvals/{approval_id}/decision",
        json={"action": "approve"},
    )
    assert res.status_code == 202
    assert res.json()["status"] == "accepted"

    def approval_resolved():
        approval = stack.projector.get_approval(approval_id)
        if not approval:
            return None
        return approval if approval["status"] == "APPROVED" else None

    approval = wait_for(approval_resolved)
    assert len(resolved) == 1
    assert resolved[0].decision == "approve"

    # VCS commit applied: the asset is now disabled.
    head_config = stack.vcs.checkout("HEAD")
    btc = next(a for a in head_config["assets"] if a["base_ticker_symbol"] == "BTC")
    assert btc["enabled"] is False


def test_agent_action_post_and_read_model(e2e_stack):
    stack = e2e_stack
    res = stack.client.post(
        "/api/v1/agent/actions",
        json={
            "type": "SEND_MESSAGE",
            "title": "E2E Alert",
            "description": "An end-to-end alert",
            "payload": {"blocks": [{"type": "markdown", "content": "E2E alert"}]},
        },
    )
    assert res.status_code == 202
    request_id = res.json()["request_id"]

    def action_completed():
        actions = stack.projector.list_actions()
        return next(
            (
                a for a in actions
                if a.get("request_id") == request_id and a.get("status") == "COMPLETED"
            ),
            None,
        )

    action = wait_for(action_completed)
    detail = stack.client.get(f"/api/v1/agent/actions/{action['id']}").json()
    assert detail["title"] == "E2E Alert"
