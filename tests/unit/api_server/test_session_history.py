from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from src.agent import AgentGateway
from src.events.message_event_bus import MessageEventBus
from src.retention.manager import RetentionManager
from src.server.app import ChatApp
from src.vcs.application.service import VCSService
from tests.unit.agent.fakes import FakeLlmAdapter
from tests.unit.api_server.helpers import (
    make_db_manager,
    make_test_llm_manager,
    make_test_trading_proxy,
)


@pytest.fixture
def client(tmp_path):
    db_manager = make_db_manager(str(tmp_path / "sessions.db"))
    vcs = VCSService(db_manager)
    app = ChatApp.create(
        trading_proxy=make_test_trading_proxy(),
        agent=AgentGateway(FakeLlmAdapter([]), vcs=vcs),
        event_bus=MessageEventBus(),
        db_manager=db_manager,
        vcs=vcs,
        llm_manager=make_test_llm_manager(db_manager),
        retention_manager=RetentionManager(db_manager),
    )
    return TestClient(app)


def test_list_sessions_derives_title_from_first_user_message(client):
    client.post(
        "/api/v1/sessions/sess-1/messages",
        json={"role": "user", "content": "Optimize BTC consensus weights for higher Sharpe"},
    )
    response = client.get("/api/v1/sessions")
    sessions = response.json()
    assert response.status_code == 200 and sessions[0]["title"] == "Optimize BTC consensus weights for higher Sharpe"


def test_delete_session_removes_conversation(client):
    client.post(
        "/api/v1/sessions/sess-del/messages",
        json={"role": "user", "content": "Hello"},
    )
    deleted = client.delete("/api/v1/sessions/sess-del")
    remaining = client.get("/api/v1/sessions").json()
    assert deleted.status_code == 200 and remaining == []


def test_delete_unknown_session_returns_404(client):
    response = client.delete("/api/v1/sessions/does-not-exist")
    assert response.status_code == 404
