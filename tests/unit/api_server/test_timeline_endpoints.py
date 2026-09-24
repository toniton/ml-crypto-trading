from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient

from src.agent import AgentGateway
from src.events.message_event_bus import MessageEventBus
from src.recorder.market_data_store import MarketDataStore
from src.server.app import ChatApp
from src.trading.events import ConsensusEvaluatedEvent
from src.vcs.application.events import RefChangedEvent
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
def event_bus():
    return MessageEventBus()


@pytest.fixture
def client(db_manager, event_bus):
    vcs = VCSService(db_manager)
    agent = AgentGateway(FakeLlmAdapter([]), vcs=vcs)
    market_store = MarketDataStore(db_manager)
    app = ChatApp.create(
        agent=agent,
        event_bus=event_bus,
        db_manager=db_manager,
        market_data_store=market_store,
        vcs=vcs,
    )
    return TestClient(app)


def test_get_timeline_empty(client):
    response = client.get("/api/v1/timeline")
    assert response.status_code == 200
    assert response.json() == []


def test_get_timeline_with_events_and_filters(client, event_bus):
    event_bus.publish(RefChangedEvent(ref="refs/heads/main", commit_hash="abc12345"))
    event_bus.publish(ConsensusEvaluatedEvent(
        symbol="ETH_USD",
        decision="SELL",
        quorum_met=True,
        buy_votes=0,
        sell_votes=3,
    ))

    # All items
    res_all = client.get("/api/v1/timeline")
    assert res_all.status_code == 200
    data = res_all.json()
    assert len(data) == 2

    # Filter category
    res_vcs = client.get("/api/v1/timeline?category=VCS")
    assert res_vcs.status_code == 200
    assert len(res_vcs.json()) == 1
    assert res_vcs.json()[0]["category"] == "VCS"

    # Filter entity_type & entity_id
    res_asset = client.get("/api/v1/timeline?entity_type=ASSET&entity_id=ETH_USD")
    assert res_asset.status_code == 200
    assert len(res_asset.json()) == 1
    assert res_asset.json()[0]["title"] == "Consensus Evaluated: ETH_USD -> SELL"

    # Pagination
    res_page = client.get("/api/v1/timeline?limit=1&offset=0")
    assert res_page.status_code == 200
    assert len(res_page.json()) == 1
