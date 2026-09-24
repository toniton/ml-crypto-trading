from __future__ import annotations

import threading
import time
from typing import Optional

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from src.agent.monitoring.activity_state import ActivityStateProvider, AssetActivityState
from src.core.interfaces.event_bus import EventBus
from src.events.agent_event_metadata import AgentEventMetadata
from src.events.agent_events import TradingActivityAnomalyDetectedEvent
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class StarvationWatchdog(ApplicationLoggingMixin):
    SCHEDULE_SECONDS: dict[int, float] = {
        AssetSchedule.EVERY_SECOND.value: 1.0,
        AssetSchedule.EVERY_MINUTE.value: 60.0,
        AssetSchedule.EVERY_HOUR.value: 3600.0,
        AssetSchedule.EVERY_DAY.value: 86400.0,
        AssetSchedule.EVERY_WEEK.value: 604800.0,
        AssetSchedule.EVERY_MONTH.value: 2592000.0,
    }

    def __init__(
            self,
            activity_provider: ActivityStateProvider,
            assets: list[Asset],
            event_bus: EventBus,
            missed_intervals_threshold: float = 3.0,
            grace_period_seconds: float = 60.0,
            fallback_threshold_seconds: float = 86400.0,
            poll_interval_seconds: float = 30.0,
    ):
        self._activity_provider = activity_provider
        self._assets = assets
        self._event_bus = event_bus
        self._missed_intervals_threshold = missed_intervals_threshold
        self._grace_period_seconds = grace_period_seconds
        self._fallback_threshold_seconds = fallback_threshold_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._started_at = time.time()
        self._triggered: set[str] = set()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def started_at(self) -> float:
        return self._started_at

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self.app_logger.warning("Starvation watchdog is already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="StarvationWatchdog"
        )
        self._thread.start()
        self.app_logger.info("Started starvation watchdog for %d assets", len(self._assets))

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                self.app_logger.warning("Starvation watchdog failed to stop within timeout")
        self.app_logger.info("Stopped starvation watchdog")

    def run_once(self) -> list[TradingActivityAnomalyDetectedEvent]:
        emitted: list[TradingActivityAnomalyDetectedEvent] = []
        for asset in self._assets:
            if not asset.enabled:
                continue
            event = self._check_asset(asset)
            if event is not None:
                emitted.append(event)
        return emitted

    def _check_asset(self, asset: Asset) -> Optional[TradingActivityAnomalyDetectedEvent]:
        ticker = asset.ticker_symbol
        state = self._activity_provider.state_for(ticker)
        now = time.time()
        threshold = self._threshold_for(asset)

        anomaly_kind = self._classify(state, now, threshold, baseline=self._baseline(state))
        if anomaly_kind is not None:
            with self._lock:
                if ticker in self._triggered:
                    return None
                self._triggered.add(ticker)
            event = TradingActivityAnomalyDetectedEvent(
                asset=ticker,
                anomaly_kind=anomaly_kind,
                activity_state=state.to_dict() if state is not None else None,
                threshold=threshold,
                detected_at=str(now),
            )
            event.agent_metadata = AgentEventMetadata(causation_id=None)
            self._event_bus.publish(event)
            self.app_logger.warning(
                f"Trading starvation detected for {ticker}: {anomaly_kind}"
            )
            return event

        with self._lock:
            if ticker in self._triggered:
                self._triggered.discard(ticker)
        return None

    def _is_starved(self, state: Optional[AssetActivityState], now: float, threshold: float) -> bool:
        return self._classify(state, now, threshold, baseline=self._baseline(state)) is not None

    def _baseline(self, _state: Optional[AssetActivityState] = None) -> float:
        return max(self._activity_provider.started_at, self._started_at)

    @classmethod
    def _classify(
            cls,
            state: Optional[AssetActivityState],
            now: float,
            threshold: float,
            baseline: Optional[float] = None,
    ) -> Optional[str]:
        base = baseline if baseline is not None else (now - threshold - 1.0)
        if state is None or cls._stale(state.last_market_data_at, now, threshold):
            last_md = state.last_market_data_at if state and state.last_market_data_at is not None else base
            if (now - last_md) > threshold:
                return "NO_MARKET_DATA"
            return None
        if cls._stale(state.last_evaluation_at, now, threshold):
            last_eval = state.last_evaluation_at if state.last_evaluation_at is not None else base
            if (now - last_eval) > threshold:
                return "NO_STRATEGY_ACTIVITY"
            return None
        last_signal = state.last_signal_at if state.last_signal_at is not None else base
        if (now - last_signal) > threshold:
            return "NO_SIGNALS"
        if state.last_signal_at is not None:
            last_order = state.last_order_at if state.last_order_at is not None else base
            if (now - last_order) > threshold:
                return "NO_ORDERS"
        if state.last_order_at is not None:
            last_execution = state.last_execution_at if state.last_execution_at is not None else base
            if (now - last_execution) > threshold:
                return "NO_EXECUTIONS"
        return None

    @staticmethod
    def _stale(value: Optional[float], now: float, threshold: float) -> bool:
        return value is None or (now - value) > threshold

    def _threshold_for(self, asset: Asset) -> float:
        schedule_value = asset.schedule.value if isinstance(asset.schedule, AssetSchedule) else asset.schedule
        if schedule_value in self.SCHEDULE_SECONDS:
            expected = self.SCHEDULE_SECONDS[schedule_value]
        else:
            expected = self._fallback_threshold_seconds
        return expected * self._missed_intervals_threshold + self._grace_period_seconds

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:  # pylint: disable=broad-except
                self.app_logger.exception("Starvation watchdog poll failed")
            self._stop_event.wait(self._poll_interval_seconds)