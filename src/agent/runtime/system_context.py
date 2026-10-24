from __future__ import annotations

from datetime import datetime, timezone
import os
import platform
import resource
import sys
import threading
from typing import Any, Optional

from src.core.interfaces.llm_adapter import LlmAdapter


def collect_machine_snapshot() -> dict[str, Any]:
    """Collects host machine, operating system, and bot process resource telemetry."""
    rss_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    process_rss_mb = round(rss_raw / divisor, 2)

    try:
        load_avg: Optional[tuple[float, float, float]] = tuple(  # type: ignore[assignment]
            round(val, 2) for val in os.getloadavg()
        )
    except (AttributeError, OSError):
        load_avg = None

    return {
        "hostname": platform.node() or "localhost",
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python_version": platform.python_version(),
        "pid": os.getpid(),
        "cpu_count": os.cpu_count() or 1,
        "load_average_1m_5m_15m": load_avg,
        "process_rss_mb": process_rss_mb,
        "active_threads": threading.active_count(),
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


def format_machine_snapshot(snapshot: Optional[dict[str, Any]] = None) -> str:
    """Formats the host machine and process telemetry snapshot for agent workflows."""
    data = snapshot or collect_machine_snapshot()
    load_tuple = data.get("load_average_1m_5m_15m")
    load_str = (
        f"{load_tuple[0]} / {load_tuple[1]} / {load_tuple[2]}"
        if isinstance(load_tuple, tuple) and len(load_tuple) == 3
        else "N/A"
    )
    return (
        "Machine & Process Runtime Context:\n"
        f"  Host / OS: {data.get('hostname')} ({data.get('os')}) | "
        f"Python {data.get('python_version')} | PID {data.get('pid')}\n"
        f"  CPU & Load: {data.get('cpu_count')} cores | Load Avg (1m/5m/15m): {load_str}\n"
        f"  Process Resources: RSS Memory {data.get('process_rss_mb')} MB | "
        f"Active Threads: {data.get('active_threads')}\n"
        f"  Snapshot Timestamp: {data.get('timestamp_utc')}"
    )


def collect_workflow_runtime_context(
    llm: Optional[LlmAdapter] = None,
    include_machine: bool = True,
    include_health: bool = True,
    include_session: bool = True,
) -> str:
    """Gathers host machine telemetry plus live bot health and session context when bound."""
    sections: list[str] = []
    if include_machine:
        sections.append(format_machine_snapshot())

    if llm is None:
        return "\n\n".join(sections)

    if include_health:
        health_tool = llm.get_tool("trading_health")
        if health_tool is not None:
            try:
                health_out = health_tool.invoke({"include_assets": True})
                if health_out:
                    sections.append(str(health_out))
            except Exception:  # pylint: disable=broad-except
                pass

    if include_session:
        session_tool = llm.get_tool("get_session_summary") or llm.get_tool("session_summary")
        if session_tool is not None:
            try:
                session_out = session_tool.invoke({})
                if session_out:
                    sections.append(str(session_out))
            except Exception:  # pylint: disable=broad-except
                pass

    return "\n\n".join(sections)
