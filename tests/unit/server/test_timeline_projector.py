from __future__ import annotations

from src.agent.monitoring.starvation_watchdog import TradingActivityAnomalyDetectedEvent
from src.events.agent_events import (
    AgentActionCompletedEvent,
    AgentActionFailedEvent,
    AgentApprovalRequestedEvent,
    AgentApprovalResolvedEvent,
)
from src.events.decision_models import (
    ActorType,
    AgentDecisionRecordedEvent,
    DecisionRecord,
    DecisionType,
    EntityRef,
)
from src.events.message_event_bus import MessageEventBus
from src.server.timeline_projector import TimelineProjector
from src.trading.events import ConsensusEvaluatedEvent
from src.vcs.application.events import RefChangedEvent


def test_agent_decision_events_projected():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus)
    projector.subscribe()

    record = DecisionRecord(
        actor_type=ActorType.AGENT,
        actor_id="strategy_manager",
        decision_type=DecisionType.INVESTIGATION_OUTCOME,
        summary="Adjusted risk limit",
        rationale="High volatility detected on BTC_USD.",
        evidence_ids=["ev-1"],
        entities=[EntityRef(type="ASSET", id="BTC_USD")],
    )
    ev1 = AgentDecisionRecordedEvent(decision=record)
    ev1.set_causality(correlation_id="c-1", asset="BTC_USD")
    bus.publish(ev1)

    items = projector.list_items()
    assert len(items) == 1
    assert items[0]["title"] == "Decision: Adjusted risk limit"
    assert items[0]["correlation_id"] == "c-1"
    assert items[0]["category"] == "DECISION"
    assert items[0]["primary_entity"]["id"] == "BTC_USD"

    projector.close()


def test_consensus_event_projected():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus)
    projector.subscribe()

    bus.publish(ConsensusEvaluatedEvent(
        symbol="ETH_USD",
        decision="BUY",
        quorum_met=True,
        buy_votes=3,
        sell_votes=0,
    ))

    items = projector.list_items(category="DECISION")
    assert len(items) == 1
    assert items[0]["category"] == "DECISION"
    assert items[0]["title"] == "Consensus Evaluated: ETH_USD -> BUY"
    assert items[0]["metadata"]["buy_votes"] == 3


def test_watchdog_anomaly_projected():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus)
    projector.subscribe()

    bus.publish(TradingActivityAnomalyDetectedEvent(
        asset="DOGE_USD",
        anomaly_kind="MARKET_DATA_STARVATION",
        threshold=120.0,
    ))

    items = projector.list_items(severity="WARNING")
    assert len(items) == 1
    assert items[0]["actor_type"] == "WATCHDOG"
    assert items[0]["primary_entity"]["id"] == "DOGE_USD"


def test_approval_events_projected():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus)
    projector.subscribe()

    bus.publish(AgentApprovalRequestedEvent(
        approval_id="app-1",
        approval_payload={"title": "Adjust BTC Quorum", "asset": "BTC_USD"},
    ))
    bus.publish(AgentApprovalResolvedEvent(
        approval_id="app-1",
        decision="approved",
    ))

    items = projector.list_items(category="APPROVAL")
    assert len(items) == 2
    assert items[0]["title"] == "Proposal Decision: APPROVED"
    assert items[1]["title"] == "Approval Requested: Adjust BTC Quorum"


def test_vcs_event_projected():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus)
    projector.subscribe()

    bus.publish(RefChangedEvent(
        ref="refs/heads/main",
        commit_hash="abcdef123456",
    ))

    items = projector.list_items(category="VCS")
    assert len(items) == 1
    assert items[0]["title"] == "VCS Updated: refs/heads/main"
    assert items[0]["primary_entity"]["id"] == "abcdef123456"


def test_filter_by_entity_type_and_id():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus)
    projector.subscribe()

    bus.publish(TradingActivityAnomalyDetectedEvent(
        asset="BTC_USD",
        anomaly_kind="MARKET_DATA_STARVATION",
        threshold=120.0,
    ))
    bus.publish(ConsensusEvaluatedEvent(symbol="ETH_USD", decision="HOLD", quorum_met=False, buy_votes=0, sell_votes=0))

    btc_items = projector.list_items(entity_type="ASSET", entity_id="BTC_USD")
    assert len(btc_items) == 1
    assert btc_items[0]["metadata"]["asset"] == "BTC_USD"

    eth_items = projector.list_items(entity_type="ASSET", entity_id="ETH_USD")
    assert len(eth_items) == 1
    assert eth_items[0]["metadata"]["decision"] == "HOLD"


def test_max_items_eviction():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus, max_items=3)
    projector.subscribe()

    for i in range(5):
        bus.publish(ConsensusEvaluatedEvent(
            symbol=f"SYM_{i}", decision="HOLD", quorum_met=False, buy_votes=0, sell_votes=0
        ))

    items = projector.list_items()
    assert len(items) == 3
    assert items[0]["title"] == "Consensus Evaluated: SYM_4 -> HOLD"
    assert items[2]["title"] == "Consensus Evaluated: SYM_2 -> HOLD"


def test_decision_recorded_event_projected():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus)
    projector.subscribe()

    record = DecisionRecord(
        actor_type=ActorType.AGENT,
        actor_id="investigation_worker",
        decision_type=DecisionType.INVESTIGATION_OUTCOME,
        summary="Risk or configuration gating",
        rationale="Starvation detected for BTC_USD. Proposing pause.",
        evidence_ids=["ev-123"],
        entities=[EntityRef(type="ASSET", id="BTC_USD")],
    )
    event = AgentDecisionRecordedEvent(decision=record)
    event.set_causality(correlation_id="corr-1", causation_id="cause-1", asset="BTC_USD")
    bus.publish(event)

    items = projector.list_items(category="DECISION")
    assert len(items) == 1
    assert items[0]["category"] == "DECISION"
    assert items[0]["title"] == "Decision: Risk or configuration gating"
    assert items[0]["summary"] == "Starvation detected for BTC_USD. Proposing pause."
    assert items[0]["correlation_id"] == "corr-1"
    assert items[0]["causation_id"] == "cause-1"
    assert items[0]["primary_entity"]["id"] == "BTC_USD"


def test_action_completed_and_failed_projected():
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus)
    projector.subscribe()

    bus.publish(AgentActionCompletedEvent(
        action_id="act-100",
        result_payload={"status": "ok"},
    ))
    bus.publish(AgentActionFailedEvent(
        action_id="act-200",
        error="Permission denied",
    ))

    items = projector.list_items(category="AGENT")
    assert len(items) == 2
    assert items[0]["title"] == "Action Failed: act-200"
    assert items[0]["severity"] == "ERROR"
    assert items[1]["title"] == "Action Completed: act-100"
    assert items[1]["severity"] == "INFO"


def test_projector_flush_and_persistence(tmp_path):
    from tests.unit.api_server.helpers import make_db_manager
    from src.database.repositories.providers.postgres_timeline_repository import PostgresTimelineRepository

    db_mgr = make_db_manager(str(tmp_path / "app.db"))
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus, db_manager=db_mgr, flush_interval_seconds=0)
    projector.subscribe()

    bus.publish(ConsensusEvaluatedEvent(
        symbol="BTC_USD",
        decision="BUY",
        quorum_met=True,
        buy_votes=3,
        sell_votes=0,
    ))

    projector.flush()

    with db_mgr.get_unit_of_work() as uow:
        repo = uow.get_repository(PostgresTimelineRepository)
        items = repo.list_items()
        assert len(items) == 1
        assert items[0].title == "Consensus Evaluated: BTC_USD -> BUY"

    projector.close()


def test_projector_eviction_boundary_flush(tmp_path):
    from tests.unit.api_server.helpers import make_db_manager
    from src.database.repositories.providers.postgres_timeline_repository import PostgresTimelineRepository

    db_mgr = make_db_manager(str(tmp_path / "app.db"))
    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus, max_items=2, db_manager=db_mgr, flush_interval_seconds=0)
    projector.subscribe()

    for i in range(3):
        bus.publish(ConsensusEvaluatedEvent(
            symbol=f"SYM_{i}",
            decision="HOLD",
            quorum_met=False,
            buy_votes=0,
            sell_votes=0,
        ))

    with db_mgr.get_unit_of_work() as uow:
        repo = uow.get_repository(PostgresTimelineRepository)
        db_items = repo.list_items(limit=10)
        assert len(db_items) == 3

    in_mem_items = projector.list_items(limit=10)
    assert len(in_mem_items) == 3

    projector.close()


def test_projector_hydration_from_persisted_timeline(tmp_path):
    from tests.unit.api_server.helpers import make_db_manager
    from src.database.repositories.providers.postgres_timeline_repository import PostgresTimelineRepository
    from src.timeline.timeline_models import TimelineCategory, TimelineItem

    db_mgr = make_db_manager(str(tmp_path / "app.db"))
    with db_mgr.get_unit_of_work() as uow:
        repo = uow.get_repository(PostgresTimelineRepository)
        repo.save(TimelineItem(
            timeline_id="seeded-1",
            category=TimelineCategory.DECISION,
            title="Historical Decision",
            summary="Seeded item",
        ))

    bus = MessageEventBus()
    projector = TimelineProjector(event_bus=bus, db_manager=db_mgr, flush_interval_seconds=0)
    projector.subscribe()

    items = projector.list_items()
    assert len(items) == 1
    assert items[0]["timeline_id"] == "seeded-1"
    assert items[0]["title"] == "Historical Decision"

    projector.close()

