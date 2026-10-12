from __future__ import annotations

from .conftest import wait_for


def test_config_read_and_commit_lifecycle(e2e_stack):
    stack = e2e_stack

    config = stack.client.get("/api/v1/config").json()
    assert config["assets"][0]["base_ticker_symbol"] == "BTC"

    original_buy = config["assets"][0]["consensus"]["buy"]

    # Commit a change through the API.
    config["assets"][0]["consensus"]["buy"] = round(float(original_buy) + 0.5, 2)
    res = stack.client.post(
        "/api/v1/config",
        json={
            "assets": config["assets"],
            "dynamic_quantity": config.get("dynamic_quantity"),
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "committed"
    commit_hash = payload["commit_hash"]

    # Change is live.
    updated = stack.client.get("/api/v1/config").json()
    assert updated["assets"][0]["consensus"]["buy"] == config["assets"][0]["consensus"]["buy"]

    # VCS history + checkout of the previous state (rollback).
    log = stack.client.get("/api/v1/vcs/log?limit=10").json()
    hashes = [entry["hash"] for entry in log]
    assert commit_hash in hashes

    def find_previous():
        for entry in log:
            if entry["hash"] != commit_hash:
                return entry["hash"]
        return None

    previous_hash = find_previous()
    assert previous_hash is not None
    previous = stack.client.get(f"/api/v1/vcs/checkout/{previous_hash}").json()
    assert previous["assets"][0]["consensus"]["buy"] == original_buy


def test_sessions_and_chat_sse(e2e_stack):
    stack = e2e_stack

    sessions = stack.client.get("/api/v1/sessions").json()
    assert isinstance(sessions, list)

    res = stack.client.post(
        "/api/v1/chat",
        json={"prompt": "What is my configuration?"},
    )
    assert res.status_code == 200
    body = res.text
    assert "event: session" in body
    assert "event: done" in body


def test_backtest_compare_and_observability(e2e_stack):
    stack = e2e_stack
    head = stack.vcs.head("HEAD").hash

    compare = stack.client.post(
        "/api/v1/agent/backtest/compare",
        json={
            "base_commit": head,
            "comparison_commit": head,
            "asset": "BTC_USD",
        },
    )
    assert compare.status_code == 200
    data = compare.json()
    assert data["base_commit"] == head
    assert len(data["differences"]) > 0

    runtime = stack.client.get("/api/v1/runtime")
    assert runtime.status_code == 200

    health = stack.client.get("/api/v1/engine/status")
    assert health.status_code == 200
    assert "is_running" in health.json()


def test_agent_actions_read_model_roundtrip(e2e_stack):
    stack = e2e_stack
    empty = stack.client.get("/api/v1/agent/actions").json()
    assert isinstance(empty, list)

    res = stack.client.post(
        "/api/v1/agent/actions",
        json={
            "type": "SEND_MESSAGE",
            "title": "Roundtrip",
            "description": "Roundtrip",
        },
    )
    assert res.status_code == 202
    request_id = res.json()["request_id"]

    def action_visible():
        actions = stack.client.get("/api/v1/agent/actions").json()
        return next(
            (a for a in actions if a.get("request_id") == request_id),
            None,
        )

    assert wait_for(action_visible) is not None
