from __future__ import annotations

import asyncio
import collections
from datetime import datetime, timezone
import resource
import sys
import threading
import time
from typing import Any, Deque, Dict, Optional

from src.metrics.models.metric_type import AggregationType, MetricType
from src.metrics.services.metric_service import MetricService


class EventLoopLagMonitor:
    def __init__(self, interval_seconds: float = 0.5, history_size: int = 120):
        self._interval_seconds = interval_seconds
        self._history_size = history_size
        self._lag_history: Deque[float] = collections.deque(maxlen=history_size)
        self._is_running = False
        self._task: Optional[asyncio.Task] = None
        self._last_tick: Optional[float] = None
        self._last_lag_ms: float = 0.0

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> asyncio.Task:
        if self._is_running and self._task and not self._task.done():
            return self._task

        self._is_running = True
        target_loop = loop or asyncio.get_event_loop()
        self._task = target_loop.create_task(self._run_loop(target_loop))
        return self._task

    def stop(self) -> None:
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _run_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        while self._is_running:
            try:
                expected = loop.time() + self._interval_seconds
                await asyncio.sleep(self._interval_seconds)
                if not self._is_running:
                    break
                actual = loop.time()
                lag_ms = max(0.0, (actual - expected) * 1000.0)
                self.record_lag(lag_ms)
            except asyncio.CancelledError:
                break
            except Exception:  # pylint: disable=broad-except
                pass

    def record_lag(self, lag_ms: float) -> None:
        self._last_lag_ms = round(lag_ms, 2)
        self._last_tick = time.time()
        self._lag_history.append(self._last_lag_ms)

    def get_stats(self) -> Dict[str, float]:
        if not self._lag_history:
            return {
                "current_ms": self._last_lag_ms,
                "p50_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0,
                "max_ms": 0.0,
            }

        sorted_samples = sorted(self._lag_history)
        n = len(sorted_samples)

        def percentile(pct: float) -> float:
            idx = int(round(pct * (n - 1)))
            return round(sorted_samples[idx], 2)

        return {
            "current_ms": self._last_lag_ms,
            "p50_ms": percentile(0.50),
            "p95_ms": percentile(0.95),
            "p99_ms": percentile(0.99),
            "max_ms": round(sorted_samples[-1], 2),
        }


class ProcessStatsTracker:
    def __init__(self):
        self._last_perf_time = time.perf_counter()
        self._last_proc_time = time.process_time()

    def get_memory_rss_bytes(self) -> int:
        try:
            import psutil  # pylint: disable=import-outside-toplevel,import-error
            return int(psutil.Process().memory_info().rss)
        except Exception:  # pylint: disable=broad-except
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if sys.platform == "darwin":
                return int(usage)
            return int(usage * 1024)

    def get_cpu_percent(self) -> float:
        try:
            import psutil  # pylint: disable=import-outside-toplevel,import-error
            return float(round(psutil.Process().cpu_percent(interval=None), 2))
        except Exception:  # pylint: disable=broad-except
            now = time.perf_counter()
            proc_now = time.process_time()
            elapsed = now - self._last_perf_time
            if elapsed <= 0:
                return 0.0
            cpu = ((proc_now - self._last_proc_time) / elapsed) * 100.0
            self._last_perf_time = now
            self._last_proc_time = proc_now
            return float(round(max(0.0, cpu), 2))

    @staticmethod
    def get_threads_count() -> int:
        return threading.active_count()


class RuntimeMetricsCollector:
    def __init__(
            self,
            metric_service: MetricService,
            lag_monitor: Optional[EventLoopLagMonitor] = None,
            process_tracker: Optional[ProcessStatsTracker] = None,
            start_time: Optional[float] = None,
    ):
        self._metric_service = metric_service
        self._lag_monitor = lag_monitor or EventLoopLagMonitor()
        self._process_tracker = process_tracker or ProcessStatsTracker()
        self._start_time = start_time or time.time()
        self._last_heartbeat = datetime.now(timezone.utc)
        self._register_definitions()

    def _register_definitions(self) -> None:
        self._metric_service.register(
            "runtime.uptime",
            metric_type=MetricType.GAUGE,
            unit="s",
            description="Process uptime in seconds",
            aggregation=AggregationType.LAST,
        )
        self._metric_service.register(
            "runtime.memory",
            metric_type=MetricType.GAUGE,
            unit="MB",
            description="Process resident set memory in MB",
            aggregation=AggregationType.LAST,
        )
        self._metric_service.register(
            "runtime.cpu",
            metric_type=MetricType.GAUGE,
            unit="%",
            description="Process CPU utilization percentage",
            aggregation=AggregationType.AVG,
        )
        self._metric_service.register(
            "runtime.threads",
            metric_type=MetricType.GAUGE,
            unit="count",
            description="Active thread count",
            aggregation=AggregationType.LAST,
        )
        self._metric_service.register(
            "runtime.event_loop_lag",
            metric_type=MetricType.HISTOGRAM,
            unit="ms",
            description="Event loop tick lag in milliseconds",
            aggregation=AggregationType.P95,
        )
        self._metric_service.register(
            "runtime.last_heartbeat",
            metric_type=MetricType.GAUGE,
            unit="timestamp",
            description="Timestamp of the latest runtime heartbeat",
            aggregation=AggregationType.LAST,
        )

    @property
    def lag_monitor(self) -> EventLoopLagMonitor:
        return self._lag_monitor

    async def start_monitoring(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> Optional[asyncio.Task]:
        target_loop = loop or asyncio.get_running_loop()
        return self._lag_monitor.start(target_loop)

    def stop_monitoring(self) -> None:
        self._lag_monitor.stop()

    def heartbeat(self) -> datetime:
        self._last_heartbeat = datetime.now(timezone.utc)
        return self._last_heartbeat

    def collect_and_record(self) -> Dict[str, Any]:  # pylint: disable=too-many-locals
        now = self.heartbeat()
        uptime_seconds = max(0.0, time.time() - self._start_time)
        rss_bytes = self._process_tracker.get_memory_rss_bytes()
        rss_mb = round(rss_bytes / (1024 * 1024), 2)
        cpu_percent = self._process_tracker.get_cpu_percent()
        threads_count = self._process_tracker.get_threads_count()
        lag_stats = self._lag_monitor.get_stats()

        self._metric_service.gauge("runtime.uptime", uptime_seconds, timestamp=now)
        self._metric_service.gauge("runtime.memory", rss_mb, timestamp=now)
        self._metric_service.gauge("runtime.cpu", cpu_percent, timestamp=now)
        self._metric_service.gauge("runtime.threads", float(threads_count), timestamp=now)
        self._metric_service.gauge("runtime.last_heartbeat", now.timestamp(), timestamp=now)
        self._metric_service.observe("runtime.event_loop_lag", lag_stats["p95_ms"], timestamp=now)
        self._metric_service.flush()

        return self.get_health_snapshot(
            uptime_seconds=uptime_seconds,
            rss_bytes=rss_bytes,
            rss_mb=rss_mb,
            cpu_percent=cpu_percent,
            threads_count=threads_count,
            lag_stats=lag_stats,
            heartbeat=now,
        )

    def get_health_snapshot(  # pylint: disable=too-many-locals
            self,
            uptime_seconds: Optional[float] = None,
            rss_bytes: Optional[int] = None,
            rss_mb: Optional[float] = None,
            cpu_percent: Optional[float] = None,
            threads_count: Optional[int] = None,
            lag_stats: Optional[Dict[str, float]] = None,
            heartbeat: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        now = heartbeat or self._last_heartbeat
        uptime = uptime_seconds if uptime_seconds is not None else max(0.0, time.time() - self._start_time)
        bytes_val = rss_bytes if rss_bytes is not None else self._process_tracker.get_memory_rss_bytes()
        mb_val = rss_mb if rss_mb is not None else round(bytes_val / (1024 * 1024), 2)
        cpu_val = cpu_percent if cpu_percent is not None else self._process_tracker.get_cpu_percent()
        threads_val = threads_count if threads_count is not None else self._process_tracker.get_threads_count()
        lag = lag_stats or self._lag_monitor.get_stats()

        status = self._derive_status(lag, cpu_val)

        return {
            "status": status,
            "uptime_seconds": round(uptime, 1),
            "uptime_formatted": self._format_uptime(uptime),
            "start_time": datetime.fromtimestamp(self._start_time, tz=timezone.utc).isoformat(),
            "last_heartbeat": now.isoformat(),
            "cpu_percent": cpu_val,
            "memory_rss_mb": mb_val,
            "memory_rss_bytes": bytes_val,
            "threads_count": threads_val,
            "event_loop_lag": lag,
        }

    @staticmethod
    def _derive_status(lag: Dict[str, float], cpu_percent: float) -> str:
        p95 = lag.get("p95_ms", 0.0)
        max_lag = lag.get("max_ms", 0.0)

        if max_lag > 5000.0:
            return "unhealthy"
        if p95 >= 50.0 or max_lag >= 500.0 or cpu_percent >= 90.0:
            return "degraded"
        return "healthy"

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        secs = int(seconds)
        days = secs // 86400
        hours = (secs % 86400) // 3600
        minutes = (secs % 3600) // 60
        remaining_secs = secs % 60

        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {minutes}m"
        if minutes > 0:
            return f"{minutes}m {remaining_secs}s"
        return f"{remaining_secs}s"
