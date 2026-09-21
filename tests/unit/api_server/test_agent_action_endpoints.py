from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient

from src.agent import AgentGateway
from src.events.message_event_bus import MessageEventBus
from src.recorder.market_data_store import MarketDataStore
from src.server.app import ChatApp
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
def app(db_manager, vcs):
    gateway = AgentGateway(FakeLlmAdapter([]), vcs=vcs)
    return ChatApp.create(
        agent=gateway,
        event_bus=MessageEventBus(),
        db_manager=db_manager,
        market_data_store=MarketDataStore(),
        vcs=vcs,
    )


@pytest.fixture
def client(app):
    return TestClient(app)


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
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COMPLETED"
    action_id = data["id"]

    list_res = client.get("/api/v1/agent/actions")
    assert list_res.status_code == 200
    actions = list_res.json()
    assert any(a["id"] == action_id for a in actions)


def test_agent_approval_flow_endpoints(client, vcs):
    head_commit = vcs.head("HEAD").hash

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
    assert res.status_code == 200

    approvals_res = client.get("/api/v1/agent/approvals?approval_status=PENDING")
    assert approvals_res.status_code == 200
    approvals = approvals_res.json()
    assert len(approvals) >= 1
    approval = approvals[0]
    approval_id = approval["id"]

    # Decide approve
    decision_res = client.post(
        f"/api/v1/agent/approvals/{approval_id}/decision",
        json={"action": "approve"},
    )
    assert decision_res.status_code == 200
    decision_body = decision_res.json()
    assert decision_body["status"] == "APPROVED"
    assert decision_body["commit_hash"] is not None


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
