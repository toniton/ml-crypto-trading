from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.agent import AgentGateway, ConfigChange, ConfigurationProposal
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.cache.cached_proposal_store import CachedProposalStore
from src.agent.router.models import AgentGoal, AgentIntent, AgentRoute
from src.database.database_manager import DatabaseManager
from src.events.message_event_bus import MessageEventBus
from src.server.app import ChatApp
from src.vcs.application.service import VCSService
from tests.unit.agent.fakes import FakeConversationStore, FakeLlmAdapter

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
def config_file(tmp_path):
    config_path = tmp_path / "trading-config.yaml"
    config_path.write_text(SAMPLE_CONFIG, encoding="utf-8")
    return str(config_path)


@pytest.fixture
def vcs(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/vcs.db", connect_args={"timeout": 30})
    DatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    db_mgr = DatabaseManager()
    db_mgr.engine = engine
    db_mgr._session_factory = session_factory

    return VCSService(db_mgr)


def _configuration_llm():
    return FakeLlmAdapter([
        AgentRoute(intent=AgentIntent.CONFIGURATION, goal=AgentGoal(objective="take more trades")),
        ConfigurationProposal(
            summary="less conservative",
            changes=[
                ConfigChange(
                    path="assets.BTC_USD.consensus.buy",
                    old_value=1.3,
                    new_value=1.1,
                    reason="more trades",
                ),
            ],
        ),
    ])


def _build_app(config_file, vcs):
    conversations = FakeConversationStore()
    gateway = AgentGateway(_configuration_llm(), config_file)
    app = ChatApp.create(
        agent=gateway,
        conversations=conversations,
        configuration_service=ConfigurationService(config_file, vcs=vcs),
        event_bus=MessageEventBus(),
    )
    return app


def _stream_and_extract_message_id(client):
    response = client.post("/api/v1/chat", json={"prompt": "make the strategy less conservative"})
    assert response.status_code == 200
    for frame in response.text.split("\n\n"):
        if "event: done" not in frame:
            continue
        for line in frame.splitlines():
            if line.startswith("data:"):
                data = json.loads(line.split("data:", 1)[1].strip())
                return data["message_id"]
    pytest.fail("done event with message_id not found in stream")


class TestProposalDecisionEndpoint:
    def test_approve_applies_and_commits_to_vcs(self, config_file, vcs):
        client = TestClient(_build_app(config_file, vcs))
        message_id = _stream_and_extract_message_id(client)

        response = client.post(
            f"/api/v1/proposals/{message_id}/decision",
            json={"action": "approve"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["action"] == "approve"
        assert body["commit_hash"]
        assert body["summary"] == "less conservative"
        assert vcs.head("HEAD").hash == body["commit_hash"]
        assert vcs.checkout("HEAD")["assets"][0]["consensus"]["buy"] == 1.1

    def test_reject_records_decision_and_blocks_reapproval(self, config_file, vcs):
        conversations = FakeConversationStore()
        app = ChatApp.create(
            agent=AgentGateway(_configuration_llm(), config_file),
            conversations=conversations,
            configuration_service=ConfigurationService(config_file, vcs=vcs),
            event_bus=MessageEventBus(),
        )
        client = TestClient(app)
        message_id = _stream_and_extract_message_id(client)

        response = client.post(
            f"/api/v1/proposals/{message_id}/decision",
            json={"action": "reject"},
        )

        assert response.status_code == 200
        assert response.json() == {"action": "reject", "message_id": message_id}

        decision = conversations.get_message(message_id)
        assert decision.payload["decision"]["action"] == "reject"
        assert "commit_hash" not in decision.payload["decision"]

        follow_up = client.post(
            f"/api/v1/proposals/{message_id}/decision",
            json={"action": "approve"},
        )
        assert follow_up.status_code == 404

    def test_approve_records_decision_message_with_commit_hash(self, config_file, vcs):
        conversations = FakeConversationStore()
        app = ChatApp.create(
            agent=AgentGateway(_configuration_llm(), config_file),
            conversations=conversations,
            configuration_service=ConfigurationService(config_file, vcs=vcs),
            event_bus=MessageEventBus(),
        )
        client = TestClient(app)
        message_id = _stream_and_extract_message_id(client)

        client.post(f"/api/v1/proposals/{message_id}/decision", json={"action": "approve"})

        decision = conversations.get_message(message_id)
        assert decision.payload["decision"]["action"] == "approve"
        assert decision.payload["decision"]["commit_hash"]
        assert decision.content.startswith("Approved configuration change:")

    def test_unknown_message_id_returns_not_found(self, config_file, vcs):
        client = TestClient(_build_app(config_file, vcs))

        response = client.post(
            "/api/v1/proposals/nope/decision",
            json={"action": "approve"},
        )

        assert response.status_code == 404

    def test_approve_invalid_proposal_returns_conflict(self, config_file, vcs):
        conversations = FakeConversationStore()
        sid = conversations.get_or_create(None)
        invalid = ConfigurationProposal(
            summary="too aggressive",
            changes=[
                ConfigChange(
                    path="assets.BTC_USD.consensus.buy",
                    old_value=1.3,
                    new_value=15.0,
                    reason="max aggressiveness",
                ),
            ],
        )
        conversations.append(
            sid,
            _assistant_message("m1", {"proposal": invalid.model_dump(mode="json")}),
        )
        app = ChatApp.create(
            agent=AgentGateway(FakeLlmAdapter(), config_file),
            conversations=conversations,
            configuration_service=ConfigurationService(config_file, vcs=vcs),
            event_bus=MessageEventBus(),
        )
        client = TestClient(app)

        response = client.post("/api/v1/proposals/m1/decision", json={"action": "approve"})

        assert response.status_code == 409
        assert "errors" in response.json()["detail"]


class TestCachedProposalStore:
    def test_cache_hit_returns_registered_proposal(self):
        conversations = FakeConversationStore()
        store = CachedProposalStore(conversations=conversations)
        proposal = ConfigurationProposal(summary="x", changes=[])
        store.register("m1", proposal)

        assert store.get("m1") is proposal

    def test_cache_miss_falls_back_to_conversation(self):
        conversations = FakeConversationStore()
        store = CachedProposalStore(conversations=conversations)
        proposal = ConfigurationProposal(summary="x", changes=[])

        sid = conversations.get_or_create(None)
        conversations.append(
            sid,
            _assistant_message("m1", {"proposal": proposal.model_dump(mode="json")}),
        )

        retrieved = store.get("m1")
        assert retrieved is not None
        assert retrieved.summary == "x"
        assert retrieved == proposal

    def test_remove_evicts_entry(self):
        store = CachedProposalStore(conversations=FakeConversationStore())
        store.register("m1", ConfigurationProposal(summary="x", changes=[]))

        store.remove("m1")
        assert store.get("m1") is None


class TestConfigurationServiceApplyToVcs:
    def test_applies_and_commits(self, config_file, vcs):
        service = ConfigurationService(config_file, vcs=vcs)
        proposal = ConfigurationProposal(
            summary="less conservative",
            changes=[
                ConfigChange(
                    path="assets.BTC_USD.consensus.buy",
                    old_value=1.3,
                    new_value=1.1,
                    reason="more trades",
                ),
            ],
        )

        commit, warnings = service.apply_proposal_to_vcs(proposal)

        assert commit.hash
        assert vcs.head("HEAD").hash == commit.hash
        assert vcs.checkout("HEAD")["assets"][0]["consensus"]["buy"] == 1.1
        assert warnings == []

    def test_requires_vcs(self, config_file):
        service = ConfigurationService(config_file)
        proposal = ConfigurationProposal(
            summary="less conservative",
            changes=[
                ConfigChange(
                    path="assets.BTC_USD.consensus.buy",
                    old_value=1.3,
                    new_value=1.1,
                    reason="more trades",
                ),
            ],
        )

        with pytest.raises(RuntimeError):
            service.apply_proposal_to_vcs(proposal)


def _assistant_message(message_id, payload):
    from src.core.interfaces.conversation_store import ConversationMessage

    return ConversationMessage(role="assistant", content="proposal", message_id=message_id, payload=payload)
