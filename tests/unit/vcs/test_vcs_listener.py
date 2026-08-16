from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.vcs.application.events import RefChangedEvent
from src.vcs.application.listener import RefChangeListener
from src.vcs.domain.commit import Commit


class FakeCursor:
    def __init__(self):
        self.executed = []

    def execute(self, sql):
        self.executed.append(sql)

    def close(self):
        pass


class FakeConnection:
    def __init__(self, payload=None):
        self.payload = payload
        self.notifies = []
        self.closed = False
        self._cursor = FakeCursor()
        self._polled = False

    def set_isolation_level(self, level):
        pass

    def cursor(self):
        return self._cursor

    def poll(self):
        if self.payload and not self._polled:
            self.notifies = [SimpleNamespace(payload=self.payload)]
            self._polled = True

    def close(self):
        self.closed = True


def _make_commit(hash_hex):
    return Commit(
        hash=hash_hex, blob_hash="0" * 64, parent_hash=None, author="toni",
        message="head", created_at=datetime.now(timezone.utc),
    )


class TestHandleNotifyPayload:
    def test_valid_payload_invokes_callback(self):
        events = []
        listener = RefChangeListener(db_manager=MagicMock(), on_event_callback=events.append)
        payload = '{"ref": "production", "commit": "' + "d" * 64 + '"}'

        listener._handle_notify_payload(payload)

        assert len(events) == 1
        assert isinstance(events[0], RefChangedEvent)
        assert events[0].ref == "production"
        assert events[0].commit_hash == "d" * 64

    def test_invalid_payload_does_not_invoke_callback(self):
        events = []
        listener = RefChangeListener(db_manager=MagicMock(), on_event_callback=events.append)

        listener._handle_notify_payload("not-json")

        assert events == []

    def test_missing_fields_default_to_head(self):
        events = []
        listener = RefChangeListener(db_manager=MagicMock(), on_event_callback=events.append)

        listener._handle_notify_payload('{}')

        assert events[0].ref == "HEAD"
        assert events[0].commit_hash == ""


class TestReconcile:
    def test_reconcile_fetches_head_and_emits_event(self):
        events = []
        mock_vcs = MagicMock()
        mock_vcs.head.return_value = _make_commit("e" * 64)
        listener = RefChangeListener(
            db_manager=MagicMock(), on_event_callback=events.append, config_vcs=mock_vcs
        )

        listener._reconcile()

        mock_vcs.head.assert_called_once_with("HEAD")
        assert len(events) == 1
        assert events[0].ref == "HEAD"
        assert events[0].commit_hash == "e" * 64

    def test_reconcile_skipped_without_config_vcs(self):
        events = []
        listener = RefChangeListener(db_manager=MagicMock(), on_event_callback=events.append)

        listener._reconcile()

        assert events == []

    def test_reconcile_handles_vcs_failure(self):
        mock_vcs = MagicMock()
        mock_vcs.head.side_effect = RuntimeError("db down")
        listener = RefChangeListener(
            db_manager=MagicMock(), on_event_callback=lambda e: None, config_vcs=mock_vcs
        )

        listener._reconcile()  # should not raise


class TestListenLoopResiliency:
    def test_reconnects_and_reconciles_head(self, monkeypatch):
        events = []
        mock_vcs = MagicMock()
        mock_vcs.head.return_value = _make_commit("f" * 64)

        listener = RefChangeListener(
            db_manager=MagicMock(), on_event_callback=events.append, config_vcs=mock_vcs
        )

        fake_conn = FakeConnection(payload='{"ref": "HEAD", "commit": "' + "g" * 64 + '"}')
        fake_engine = MagicMock()
        connect_attempts = {"n": 0}

        def raw_connection():
            connect_attempts["n"] += 1
            if connect_attempts["n"] == 1:
                raise ConnectionError("first connect fails")
            return fake_conn

        fake_engine.raw_connection = raw_connection
        listener.db_manager.get_engine = MagicMock(return_value=fake_engine)

        def fake_select(_, __, ___, ____):
            listener._stop_event.set()
            return ([], [], [])

        monkeypatch.setattr("src.vcs.application.listener.select.select", fake_select)
        monkeypatch.setattr("src.vcs.application.listener.time.sleep", lambda _: None)

        listener._listen_loop()

        assert connect_attempts["n"] == 2  # failed once, then reconnected
        assert fake_conn._cursor.executed == ["LISTEN vcs_ref_update;"]
        assert fake_conn.closed is True
        # Reconciliation after reconnect emits HEAD event
        assert any(e.commit_hash == "f" * 64 for e in events), events
        mock_vcs.head.assert_called_once_with("HEAD")

    def test_forwards_notify_event_after_subscribe(self, monkeypatch):
        events = []
        listener = RefChangeListener(db_manager=MagicMock(), on_event_callback=events.append)

        fake_conn = FakeConnection(payload='{"ref": "staging", "commit": "' + "h" * 64 + '"}')
        fake_engine = MagicMock()
        fake_engine.raw_connection = MagicMock(return_value=fake_conn)
        listener.db_manager.get_engine = MagicMock(return_value=fake_engine)

        def fake_select(_, __, ___, ____):
            listener._stop_event.set()
            return ([fake_conn], [], [])

        monkeypatch.setattr("src.vcs.application.listener.select.select", fake_select)
        monkeypatch.setattr("src.vcs.application.listener.time.sleep", lambda _: None)

        listener._listen_loop()

        assert any(e.ref == "staging" and e.commit_hash == "h" * 64 for e in events), events
