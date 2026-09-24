from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.repositories.providers.postgres_timeline_repository import PostgresTimelineRepository
from src.database.sqlalchemy_database_manager import SqlAlchemyDatabaseManager
from src.events.decision_models import EntityRef
from src.timeline.timeline_models import TimelineCategory, TimelineItem


def setup_in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    SqlAlchemyDatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def test_save_and_get_timeline_item():
    session = setup_in_memory_db()
    repo = PostgresTimelineRepository(database_session=session)

    item = TimelineItem(
        timeline_id="tl-123",
        timestamp=datetime(2026, 9, 24, 20, 0, 0, tzinfo=timezone.utc).isoformat(),
        category=TimelineCategory.DECISION,
        severity="INFO",
        title="Test Decision",
        summary="Test summary",
        correlation_id="corr-1",
        causation_id="cause-1",
        actor_type="AGENT",
        actor_id="agent-007",
        primary_entity=EntityRef(type="ASSET", id="BTC_USD"),
        entities=[EntityRef(type="ASSET", id="BTC_USD")],
        metadata={"key": "val"},
    )

    saved = repo.save(item)
    assert saved.timeline_id == "tl-123"

    fetched = repo.get("tl-123")
    assert fetched is not None
    assert fetched.timeline_id == "tl-123"
    assert fetched.title == "Test Decision"
    assert fetched.category == TimelineCategory.DECISION
    assert fetched.primary_entity is not None
    assert fetched.primary_entity.id == "BTC_USD"
    assert fetched.metadata == {"key": "val"}


def test_save_batch_and_list_items_with_filter():
    session = setup_in_memory_db()
    repo = PostgresTimelineRepository(database_session=session)

    item1 = TimelineItem(
        timeline_id="tl-1",
        timestamp=datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc).isoformat(),
        category=TimelineCategory.DECISION,
        severity="INFO",
        title="Decision 1",
        primary_entity=EntityRef(type="ASSET", id="BTC_USD"),
    )
    item2 = TimelineItem(
        timeline_id="tl-2",
        timestamp=datetime(2026, 9, 24, 11, 0, 0, tzinfo=timezone.utc).isoformat(),
        category=TimelineCategory.RUNTIME,
        severity="ERROR",
        title="Runtime Error 1",
        primary_entity=EntityRef(type="INCIDENT", id="inc-1"),
    )

    repo.save_batch([item1, item2])

    all_items = repo.list_items(limit=10)
    assert len(all_items) == 2
    # Ordered descending by timestamp
    assert all_items[0].timeline_id == "tl-2"
    assert all_items[1].timeline_id == "tl-1"

    decision_items = repo.list_items(category="DECISION")
    assert len(decision_items) == 1
    assert decision_items[0].timeline_id == "tl-1"

    asset_items = repo.list_items(entity_type="ASSET", entity_id="BTC_USD")
    assert len(asset_items) == 1
    assert asset_items[0].timeline_id == "tl-1"
