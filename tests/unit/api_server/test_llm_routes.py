from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient

from src.agent import AgentGateway
from src.configuration.llm_config import (
    LlmConfig,
    LlmModelConfig,
    LlmProvider,
    ToolConfig,
    ToolRegistryConfig,
)
from src.events.message_event_bus import MessageEventBus
from src.llm.llm_runtime_manager import LlmRuntimeManager
from src.recorder.market_data_store import MarketDataStore
from src.server.app import ChatApp
from src.vcs.application.service import VCSService
from tests.unit.agent.fakes import FakeLlmAdapter
from tests.unit.api_server.helpers import make_db_manager

SAMPLE_CONFIG = """
assets:
  - name: "Bitcoin"
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
def event_bus():
    return MessageEventBus()


@pytest.fixture
def llm_config():
    return LlmConfig.model_construct(
        models=[
            LlmModelConfig(
                id="groq-qwen",
                name="Groq Qwen",
                provider=LlmProvider.GROQ,
                model_name="qwen/qwen3.8-27b",
                default=True,
            ),
            LlmModelConfig(
                id="gemini-3-flash",
                name="Google Gemini",
                provider=LlmProvider.GEMINI,
                model_name="gemini-3-flash-preview",
                default=False,
            ),
        ],
        tools=ToolRegistryConfig(
            bot_tools=[
                ToolConfig(name="trading_context", enabled=True, category="market", description="Market context"),
                ToolConfig(name="exchange_fees", enabled=False, category="trading", description="Exchange fees"),
            ]
        ),
    )


@pytest.fixture
def client(db_manager, event_bus, llm_config, monkeypatch):
    monkeypatch.setattr(
        "src.llm.model_factory.ModelFactory.create_model",
        lambda *args, **kwargs: FakeLlmAdapter([]),
    )
    vcs = VCSService(db_manager)
    agent = AgentGateway(FakeLlmAdapter([]), vcs=vcs)
    market_store = MarketDataStore(db_manager)
    llm_manager = LlmRuntimeManager(llm_config=llm_config, db_manager=db_manager)
    app = ChatApp.create(
        agent=agent,
        event_bus=event_bus,
        db_manager=db_manager,
        market_data_store=market_store,
        vcs=vcs,
        llm_manager=llm_manager,
    )
    return TestClient(app)


def test_list_models_and_tools_endpoints(client):
    res_models = client.get("/api/v1/llm/models")
    assert res_models.status_code == 200
    data = res_models.json()
    assert len(data["models"]) == 2
    assert data["active_model_id"] == "groq-qwen"

    res_tools = client.get("/api/v1/llm/tools")
    assert res_tools.status_code == 200
    tools_data = res_tools.json()
    assert len(tools_data["tools"]) == 2


def test_save_credentials_and_switch_active_model(client):
    res_save = client.post(
        "/api/v1/llm/credentials",
        json={
            "model_id": "gemini-3-flash",
            "api_key": "gemini-secret-api-key",
            "api_base_url": "https://custom.gemini.api",
        },
    )
    assert res_save.status_code == 200
    assert res_save.json()["status"] == "saved"

    # Switch active model to gemini-3-flash
    res_switch = client.post(
        "/api/v1/llm/active",
        json={"model_id": "gemini-3-flash"},
    )
    assert res_switch.status_code == 200
    assert res_switch.json()["active_model_id"] == "gemini-3-flash"

    # Check active endpoint
    res_active = client.get("/api/v1/llm/active")
    assert res_active.status_code == 200
    active_data = res_active.json()
    assert active_data["active_model_id"] == "gemini-3-flash"
    assert active_data["active_model"]["has_api_key"] is True
    assert "••••••••" in active_data["active_model"]["masked_api_key"]


def test_test_connection_and_delete_credentials(client):
    res_test = client.post(
        "/api/v1/llm/test-connection",
        json={"model_id": "groq-qwen"},
    )
    assert res_test.status_code == 200
    assert res_test.json()["status"] == "connected"

    # Save credential first
    client.post(
        "/api/v1/llm/credentials",
        json={"model_id": "gemini-3-flash", "api_key": "secret-key"},
    )

    res_del = client.delete("/api/v1/llm/credentials/gemini-3-flash")
    assert res_del.status_code == 200
    assert res_del.json()["deleted"] is True
