import threading
import time
from typing import Callable

from schedule import Job, run_pending

from api.interfaces.asset import Asset
from src.core.interfaces.trading_scheduler import TradingScheduler


class LiveTradingScheduler(TradingScheduler):
    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()

    def _create_tick_func(self, callback: Callable, assets: list[Asset]) -> Callable:
        return lambda: callback(assets)

    def start(self, callback: Callable[[list[Asset]], None]):
        for asset_schedule in self.get_registered_schedules():
            schedule_factory = self.UNIT_MAP[asset_schedule]
            assets = self.get_assets(asset_schedule)
            tick_func = self._create_tick_func(callback, assets)
            self._start_schedule_thread(schedule_factory, asset_schedule, tick_func)

    def _start_schedule_thread(self, schedule_factory: Callable[[], Job], asset_schedule, tick_fn):
        def loop():
            schedule_job = schedule_factory()
            schedule_job.do(tick_fn)
            sleep_interval = self.UNIT_SECONDS[asset_schedule]
            while not self._stop_event.is_set():
                run_pending()
                time.sleep(sleep_interval)

        schedule_thread = threading.Thread(target=loop)
        schedule_thread.start()
        # schedule_thread.join()

    def stop(self):
        self._stop_event.set()
