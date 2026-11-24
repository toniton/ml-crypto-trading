from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

from api.interfaces.market_data import MarketData
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.recorder.market_data_store import MarketDataStore

DEFAULT_SNAPSHOT_FILENAME = "rio_market_data_store.json"
DEFAULT_FLUSH_INTERVAL_SECONDS = 300.0
SNAPSHOT_SCHEMA_VERSION = 1
_JOIN_TIMEOUT_SECONDS = 5.0


def default_snapshot_path() -> Path:
    return Path(tempfile.gettempdir()) / DEFAULT_SNAPSHOT_FILENAME


def _serialize_market_data(item: MarketData) -> dict[str, Any]:
    return {
        "volume": str(item.volume),
        "high_price": str(item.high_price),
        "low_price": str(item.low_price),
        "close_price": str(item.close_price),
        "timestamp": float(item.timestamp),
        "bid_price": str(item.bid_price) if item.bid_price is not None else None,
        "ask_price": str(item.ask_price) if item.ask_price is not None else None,
    }


def _deserialize_market_data(raw: dict[str, Any]) -> MarketData:
    return MarketData(
        volume=Decimal(str(raw["volume"])),
        high_price=Decimal(str(raw["high_price"])),
        low_price=Decimal(str(raw["low_price"])),
        close_price=Decimal(str(raw["close_price"])),
        timestamp=float(raw["timestamp"]),
        bid_price=Decimal(str(raw["bid_price"])) if raw.get("bid_price") is not None else None,
        ask_price=Decimal(str(raw["ask_price"])) if raw.get("ask_price") is not None else None,
    )


class MarketDataSnapshotPersistence(ApplicationLoggingMixin):
    def __init__(
            self,
            store: MarketDataStore,
            snapshot_path: Optional[Path] = None,
            flush_interval_seconds: float = DEFAULT_FLUSH_INTERVAL_SECONDS,
    ) -> None:
        self._store = store
        self._snapshot_path = snapshot_path if snapshot_path is not None else default_snapshot_path()
        self._flush_interval_seconds = flush_interval_seconds
        self._io_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._flush_thread: Optional[threading.Thread] = None

    @property
    def snapshot_path(self) -> Path:
        return self._snapshot_path

    def save(self) -> int:
        exported = self._store.export_observations()
        payload = {
            "version": SNAPSHOT_SCHEMA_VERSION,
            "saved_at": time.time(),
            "tickers": {
                ticker: [_serialize_market_data(item) for item in items]
                for ticker, items in exported.items()
            },
        }
        total = sum(len(items) for items in exported.values())

        with self._io_lock:
            self._write_atomic(payload)
        return total

    def _write_atomic(self, payload: dict[str, Any]) -> None:
        parent_dir = self._snapshot_path.parent
        parent_dir.mkdir(parents=True, exist_ok=True)
        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(parent_dir),
                prefix=f".{self._snapshot_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as tmp_file:
                temp_path = Path(tmp_file.name)
                json.dump(payload, tmp_file)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(str(temp_path), str(self._snapshot_path))
        except OSError as exc:
            self.app_logger.warning(
                "Failed to persist market data snapshot to %s: %s",
                self._snapshot_path,
                exc,
            )
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def load(self, now_epoch: Optional[float] = None) -> int:
        if not self._snapshot_path.exists():
            return 0

        try:
            with self._io_lock:
                raw_text = self._snapshot_path.read_text(encoding="utf-8")
            payload = json.loads(raw_text)
        except (OSError, json.JSONDecodeError) as exc:
            self.app_logger.warning(
                "Failed to read market data snapshot from %s; continuing without hydrated data: %s",
                self._snapshot_path,
                exc,
            )
            return 0

        if not isinstance(payload, dict) or not isinstance(payload.get("tickers"), dict):
            self.app_logger.warning(
                "Market data snapshot %s has invalid format; continuing without hydrated data.",
                self._snapshot_path,
            )
            return 0

        observations_by_ticker = self._parse_tickers(payload["tickers"])
        loaded = self._store.import_observations(observations_by_ticker, now_epoch=now_epoch)
        self.app_logger.info(
            "Hydrated %d market data observations across %d tickers from %s",
            loaded,
            len(observations_by_ticker),
            self._snapshot_path,
        )
        return loaded

    def _parse_tickers(self, raw_tickers: dict[str, Any]) -> dict[str, list[MarketData]]:
        parsed: dict[str, list[MarketData]] = {}
        for ticker, raw_items in raw_tickers.items():
            if not isinstance(ticker, str) or not isinstance(raw_items, list):
                continue
            valid_items: list[MarketData] = []
            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    continue
                try:
                    valid_items.append(_deserialize_market_data(raw_item))
                except (KeyError, TypeError, ValueError, InvalidOperation):
                    continue
            if valid_items:
                parsed[ticker] = valid_items
        return parsed

    def start_periodic_flush(self) -> None:
        if self._flush_interval_seconds <= 0:
            return
        if self._flush_thread is not None and self._flush_thread.is_alive():
            return
        self._stop_event.clear()
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            name="MarketDataSnapshotFlush",
            daemon=True,
        )
        self._flush_thread.start()

    def _flush_loop(self) -> None:
        while not self._stop_event.wait(self._flush_interval_seconds):
            try:
                self.save()
            except Exception as exc:  # pylint: disable=broad-except
                self.app_logger.warning("Periodic market data snapshot flush failed: %s", exc)

    def stop_and_flush(self) -> None:
        self._stop_event.set()
        if self._flush_thread is not None and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=_JOIN_TIMEOUT_SECONDS)
        self._flush_thread = None
        try:
            self.save()
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.warning("Final market data snapshot flush failed: %s", exc)
