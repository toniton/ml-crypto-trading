from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List

from schedule import Scheduler

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from src.configuration.trading_config import LlmSettings
from src.core.interfaces.trading_scheduler import TradingScheduler
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin


class LlmOracleScheduler(TradingScheduler, ApplicationLoggingMixin):
    def __init__(self, settings: LlmSettings):
        super().__init__()
        self._settings: LlmSettings = settings
        self._scheduler: Scheduler = Scheduler()
        self._stop_event: threading.Event = threading.Event()
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=15)
        self._scheduler_thread: threading.Thread | None = None

    def start(self, callback: Callable[[List[Asset]], None]):
        self._start_schedule(self._settings.schedule, callback)

    def _start_schedule(
            self,
            asset_schedule: AssetSchedule,
            callback: Callable[[list[Asset]], None],
    ) -> None:
        assets = self.get_assets(asset_schedule).copy()
        schedule_factory = self.UNIT_MAP[asset_schedule]

        def job() -> None:
            self._executor.submit(self._run_safe, callback, assets, asset_schedule)

        schedule_factory(self._scheduler).do(job)

        thread = threading.Thread(
            target=self._run_loop,
            args=(self._scheduler, self._stop_event, asset_schedule),
            daemon=True,
            name=f"scheduler-{asset_schedule}",
        )
        thread.start()
        self._scheduler_thread = thread

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

    def stop(self):
        self._stop_event.set()
        if self._scheduler_thread is None:
            self.app_logger.warning("Scheduler thread was not started")
            return
        thread = self._scheduler_thread
        thread.join(timeout=5)
        if thread.is_alive():
            self.app_logger.warning(
                "Scheduler thread did not exit within timeout"
            )
        executor = self._executor
        if executor:
            executor.shutdown(wait=True)
