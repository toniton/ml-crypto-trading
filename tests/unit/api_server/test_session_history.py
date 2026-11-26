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


from src.core.interfaces.conversation_store import (
    RESERVED_AGENT_SESSION_ID,
    RESERVED_AGENT_SESSION_TITLE,
)


def test_delete_unknown_session_returns_404(client):
    response = client.delete("/api/v1/sessions/does-not-exist")
    assert response.status_code == 404


def test_reserved_agent_session_is_tagged_read_write_and_cannot_be_deleted(client):
    client.post(
        f"/api/v1/sessions/{RESERVED_AGENT_SESSION_ID}/messages",
        json={"role": "assistant", "content": "Autonomous diagnostic update"},
    )
    # User can reply directly in the reserved agent session
    reply = client.post(
        f"/api/v1/sessions/{RESERVED_AGENT_SESSION_ID}/messages",
        json={"role": "user", "content": "Why did BTC stop trading?"},
    )
    assert reply.status_code == 200

    sessions = client.get("/api/v1/sessions").json()
    reserved = next(s for s in sessions if s["id"] == RESERVED_AGENT_SESSION_ID)
    assert reserved["is_reserved"] is True
    assert reserved["session_kind"] == "agent"
    assert reserved["title"] == RESERVED_AGENT_SESSION_TITLE
    assert reserved["message_count"] == 2

    delete_resp = client.delete(f"/api/v1/sessions/{RESERVED_AGENT_SESSION_ID}")
    assert delete_resp.status_code == 403
