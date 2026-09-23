from __future__ import annotations

import time
from typing import Callable

import pytest
import yaml
from fastapi.testclient import TestClient

from src.agent import AgentGateway
from src.agent.actions import (
    AgentActionExecutor,
    AgentActionService,
    AgentApprovalService,
)
from src.agent.automation import AutomationController, InvestigateActivityAnomaly
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.monitoring.starvation_watchdog import StarvationWatchdog
from src.events.message_event_bus import MessageEventBus
from src.recorder.market_data_store import MarketDataStore
from src.server.app import ChatApp
from src.trading.activity.asset_activity_tracker import AssetActivityTracker
from src.vcs.application.service import VCSService
from tests.unit.agent.fakes import FakeLlmAdapter
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


@pytest.fixture
def db_manager(tmp_path):
    db_mgr = make_db_manager(str(tmp_path / "app.db"))
    VCSService(db_mgr).seed_if_empty(yaml.safe_load(SAMPLE_CONFIG), author="test", message="seed")
    return db_mgr


@pytest.fixture
def vcs(db_manager):
    return VCSService(db_manager)


@pytest.fixture
def event_bus():
    return MessageEventBus()


@pytest.fixture
def automation(vcs, event_bus):
    action_service = AgentActionService(event_bus=event_bus)
    config_service = ConfigurationService(vcs=vcs)
    approval_service = AgentApprovalService(
        vcs=vcs,
        configuration_service=config_service,
        action_service=action_service,
        event_bus=event_bus,
    )
    executor = AgentActionExecutor(
        action_service=action_service,
        approval_service=approval_service,
        vcs=vcs,
        configuration_service=config_service,
    )
    tracker = AssetActivityTracker()
    investigation = InvestigateActivityAnomaly(activity_provider=tracker)
    watchdog = StarvationWatchdog(
        activity_provider=tracker,
        assets=[],
        event_bus=event_bus,
        poll_interval_seconds=0.1,
    )
    controller = AutomationController(
        event_bus=event_bus,
        executor=executor,
        approval_service=approval_service,
        investigation=investigation,
        watchdog=watchdog,
    )
    controller.start()
    yield controller, executor
    controller.stop()


@pytest.fixture
def app(db_manager, vcs, event_bus, automation):
    gateway = AgentGateway(FakeLlmAdapter([]), vcs=vcs)
    _, executor = automation
    return ChatApp.create(
        agent=gateway,
        event_bus=event_bus,
        db_manager=db_manager,
        market_data_store=MarketDataStore(),
        vcs=vcs,
        compare_backtest=executor.compare_backtest_drift,
    )


@pytest.fixture
def client(app):
    return TestClient(app)


def wait_for(predicate: Callable, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for asynchronous agent processing")


def test_create_and_list_agent_actions(client):
    res = client.post(
        "/api/v1/agent/actions",
        json={
            "type": "SEND_MESSAGE",
            "title": "Drift Alert",
            "description": "Backtest drift detected on BTC_USD",
            "payload": {"blocks": [{"type": "markdown", "content": "Drift alert"}]},
        },
    )
    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "accepted"
    request_id = data["request_id"]

    assert wait_for(
        lambda: any(
            a.get("request_id") == request_id and a.get("status") == "COMPLETED"
            for a in client.get("/api/v1/agent/actions").json()
        )
    )

    list_res = client.get("/api/v1/agent/actions")
    assert list_res.status_code == 200
    assert any(a.get("request_id") == request_id for a in list_res.json())


def test_agent_approval_flow_endpoints(client, vcs):
    # Create proposal action which triggers approval
    res = client.post(
        "/api/v1/agent/actions",
        json={
            "type": "APPLY_CONFIGURATION",
            "title": "Update Consensus Threshold",
            "description": "Change BTC buy threshold",
            "requires_approval": True,
            "payload": {
                "proposed_change": {
                    "changes": [
                        {
                            "path": "assets.BTC_USD.consensus.buy",
                            "old_value": 1.3,
                            "new_value": 1.0,
                            "reason": "Optimize trade entries",
                        }
                    ]
                }
            },
        },
    )
    assert res.status_code == 202

    def get_pending_approval():
        approvals = client.get("/api/v1/agent/approvals?approval_status=PENDING").json()
        return approvals[0] if approvals else None

    approval = wait_for(get_pending_approval)
    approval_id = approval["id"]

    decision_res = client.post(
        f"/api/v1/agent/approvals/{approval_id}/decision",
        json={"action": "approve"},
    )
    assert decision_res.status_code == 202
    assert decision_res.json()["status"] == "accepted"

    def approval_approved():
        approvals = client.get("/api/v1/agent/approvals?approval_status=APPROVED").json()
        return any(a["id"] == approval_id for a in approvals)

    assert wait_for(approval_approved)
    assert vcs.head("HEAD").hash is not None
    assert vcs.checkout("HEAD")["assets"][0]["consensus"]["buy"] == 1.0


def test_backtest_compare_endpoint(client, vcs):
    head_commit = vcs.head("HEAD").hash
    res = client.post(
        "/api/v1/agent/backtest/compare",
        json={
            "base_commit": head_commit,
            "comparison_commit": head_commit,
            "asset": "BTC_USD",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["base_commit"] == head_commit
    assert "differences" in data
    assert len(data["differences"]) > 0


def test_agent_websocket_connection(client):
    with client.websocket_connect("/api/v1/agent/ws") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "connected"
        assert data["channel"] == "agent"
        websocket.send_text("ping")
        resp = websocket.receive_text()
        assert resp == "pong"