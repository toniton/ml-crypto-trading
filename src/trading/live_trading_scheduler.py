from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from schedule import Scheduler

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from src.core.interfaces.trading_scheduler import TradingScheduler
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class LiveTradingScheduler(TradingScheduler, ApplicationLoggingMixin):
    def __init__(self):
        super().__init__()
        self._schedulers: dict[AssetSchedule, Scheduler] = {}
        self._scheduler_threads: dict[AssetSchedule, threading.Thread] = {}
        self._stop_events: dict[AssetSchedule, threading.Event] = {}
        self._executors: dict[AssetSchedule, ThreadPoolExecutor] = {}
        self._callback: Callable[[list[Asset]], None] | None = None
        self._lock = threading.Lock()

    def start(self, callback: Callable[[list[Asset]], None]) -> None:
        with self._lock:
            self._callback = callback
            if self._scheduler_threads:
                self.app_logger.warning("Scheduler already running")
                return

            self.app_logger.info("Starting scheduler")

            for asset_schedule in self.get_registered_schedules():
                self._start_schedule(asset_schedule, callback)

    def stop(self, asset_schedule: AssetSchedule | None = None) -> None:
        with self._lock:
            self.app_logger.info("Stopping scheduler")

            schedules = (
                [asset_schedule]
                if asset_schedule is not None
                else list(self._scheduler_threads.keys())
            )

            for schedule_key in schedules:
                stop_event = self._stop_events.get(schedule_key)
                if stop_event:
                    stop_event.set()

            for schedule_key in schedules:
                thread = self._scheduler_threads.get(schedule_key)
                if thread:
                    thread.join(timeout=5)
                    if thread.is_alive():
                        self.app_logger.warning(
                            f"Scheduler thread {schedule_key} did not exit within timeout"
                        )

            for schedule_key in schedules:
                executor = self._executors.get(schedule_key)
                if executor:
                    executor.shutdown(wait=True)

            for schedule_key in schedules:
                self._cleanup(schedule_key)

    def update_schedules(
            self,
            assets: list[Asset],
            callback: Callable[[list[Asset]], None] | None = None,
    ) -> None:
        with self._lock:
            cb = callback or self._callback
            self._callback = cb
            was_running = bool(self._scheduler_threads)

            if was_running:
                for schedule_key in list(self._scheduler_threads.keys()):
                    stop_event = self._stop_events.get(schedule_key)
                    if stop_event:
                        stop_event.set()

                for schedule_key, thread in list(self._scheduler_threads.items()):
                    if thread:
                        thread.join(timeout=5)

                for schedule_key, executor in list(self._executors.items()):
                    if executor:
                        executor.shutdown(wait=True)

                for schedule_key in list(self._scheduler_threads.keys()):
                    self._cleanup(schedule_key)

            self.clear_assets()
            self.register_assets(assets)

            if was_running and cb:
                for asset_schedule in self.get_registered_schedules():
                    self._start_schedule(asset_schedule, cb)
                self.app_logger.info(
                    "Updated live trading scheduler cadences for %d assets: %s",
                    len(assets),
                    [s.value for s in self.get_registered_schedules()],
                )

    def _start_schedule(
            self,
            asset_schedule: AssetSchedule,
            callback: Callable[[list[Asset]], None],
    ) -> None:
        scheduler = Scheduler()
        stop_event = threading.Event()
        executor = ThreadPoolExecutor(max_workers=5)

        assets = self.get_assets(asset_schedule).copy()
        schedule_factory = self.UNIT_MAP[asset_schedule]

        self._schedulers[asset_schedule] = scheduler
        self._stop_events[asset_schedule] = stop_event
        self._executors[asset_schedule] = executor

        def job() -> None:
            executor.submit(self._run_safe, callback, assets, asset_schedule)

        schedule_factory(scheduler).do(job)

        thread = threading.Thread(
            target=self._run_loop,
            args=(scheduler, stop_event, asset_schedule),
            daemon=True,
            name=f"scheduler-{asset_schedule}",
        )
        thread.start()
        self._scheduler_threads[asset_schedule] = thread

    def _run_loop(
            self,
            scheduler: Scheduler,
            stop_event: threading.Event,
            asset_schedule: AssetSchedule,
    ) -> None:
        while not stop_event.is_set():
            try:
                scheduler.run_pending()
                idle = scheduler.idle_seconds
                sleep_for = idle if idle and idle > 0 else 1.0
                stop_event.wait(sleep_for)
            except Exception:
                self.app_logger.exception(
                    f"Error in scheduler loop: {asset_schedule}"
                )

    def _run_safe(
            self,
            callback: Callable[[list[Asset]], None],
            assets: list[Asset],
            asset_schedule: AssetSchedule,
    ) -> None:
        try:
            callback(assets)
        except Exception:
            self.app_logger.exception(
                f"Callback failed: {asset_schedule}"
            )

    def _cleanup(self, asset_schedule: AssetSchedule) -> None:
        self._schedulers.pop(asset_schedule, None)
        self._stop_events.pop(asset_schedule, None)
        self._executors.pop(asset_schedule, None)
        self._scheduler_threads.pop(asset_schedule, None)
