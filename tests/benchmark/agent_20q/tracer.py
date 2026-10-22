from __future__ import annotations
# pylint: disable=protected-access

import time
from typing import Any, Dict, List, Optional

from tests.benchmark.agent_20q.models import ToolExecutionRecord


class TracedToolProxy:
    """Proxies a tool invocation and records arguments, return values, latency and status."""

    def __init__(self, key_name: str, tool: Any, tracer: BenchmarkToolTracer) -> None:
        self._key_name = key_name
        self._tool = tool
        self._tracer = tracer
        self.name = getattr(tool, "name", key_name)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        start_ns = time.perf_counter_ns()
        call_args: Dict[str, Any] = {}
        if args:
            if len(args) == 1 and isinstance(args[0], dict):
                call_args.update(args[0])
            else:
                call_args["positional_args"] = list(args)
        if kwargs:
            call_args.update(kwargs)

        status = "success"
        error_msg: Optional[str] = None
        result: Any = None
        try:
            result = self._tool.invoke(*args, **kwargs)
            return result
        except Exception as exc:  # pylint: disable=broad-exception-caught
            status = "error"
            error_msg = str(exc)
            raise
        finally:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
            output_str = str(result) if result is not None else (error_msg or "")
            self._tracer.record(
                ToolExecutionRecord(
                    tool_name=self._key_name,
                    arguments=call_args,
                    output=result,
                    output_text=output_str,
                    latency_ms=elapsed_ms,
                    status=status,
                    error_message=error_msg,
                )
            )

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        # Some LangChain tools invoke _run directly
        if hasattr(self._tool, "_run"):
            start_ns = time.perf_counter_ns()
            call_args = {"args": args, "kwargs": kwargs}
            status = "success"
            error_msg = None
            result = None
            try:
                result = self._tool._run(*args, **kwargs)
                return result
            except Exception as exc:  # pylint: disable=broad-exception-caught
                status = "error"
                error_msg = str(exc)
                raise
            finally:
                elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
                output_str = str(result) if result is not None else (error_msg or "")
                self._tracer.record(
                    ToolExecutionRecord(
                        tool_name=self._key_name,
                        arguments=call_args,
                        output=result,
                        output_text=output_str,
                        latency_ms=elapsed_ms,
                        status=status,
                        error_message=error_msg,
                    )
                )
        return self.invoke(*args, **kwargs)

    def __getattr__(self, item: str) -> Any:
        attr = getattr(self._tool, item)
        if item == "backtest_service" and attr is not None:
            class BacktestServiceProxy:
                def __init__(self, svc: Any, proxy: TracedToolProxy) -> None:
                    self._svc = svc
                    self._proxy = proxy

                def run(self, *args: Any, **kwargs: Any) -> Any:
                    start_ns = time.perf_counter_ns()
                    res = self._svc.run(*args, **kwargs)
                    elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
                    out_text = getattr(res, "report_markdown", str(res))
                    self._proxy._tracer.record(
                        ToolExecutionRecord(
                            tool_name=self._proxy._key_name,
                            arguments={"args": list(args), **kwargs},
                            output=res,
                            output_text=out_text,
                            latency_ms=elapsed_ms,
                            status="success",
                        )
                    )
                    return res

                def __getattr__(self, sub_item: str) -> Any:
                    return getattr(self._svc, sub_item)

            return BacktestServiceProxy(attr, self)
        return attr


class BenchmarkToolTracer:
    """Manages traced tool execution records during benchmark runs."""

    def __init__(self) -> None:
        self.records: List[ToolExecutionRecord] = []

    def record(self, rec: ToolExecutionRecord) -> None:
        self.records.append(rec)

    def clear(self) -> None:
        self.records.clear()

    def get_invoked_tool_names(self) -> List[str]:
        names: List[str] = []
        for r in self.records:
            if r.tool_name not in names:
                names.append(r.tool_name)
        return names

    def get_records_for_tool(self, tool_name: str) -> List[ToolExecutionRecord]:
        target = tool_name.lower()
        return [r for r in self.records if r.tool_name.lower() == target]

    def get_combined_evidence_text(self) -> str:
        return "\n\n".join(r.output_text for r in self.records if r.output_text)

    def wrap_tools(self, tools: Dict[str, Any]) -> Dict[str, Any]:
        """Returns a new dictionary with tools wrapped in TracedToolProxy."""
        wrapped: Dict[str, Any] = {}
        for key, tool in tools.items():
            if isinstance(tool, TracedToolProxy):
                wrapped[key] = tool
            else:
                wrapped[key] = TracedToolProxy(key, tool, self)
        return wrapped
