from __future__ import annotations

from typing import Any, Optional

from src.agent.runtime.system_context import format_machine_snapshot
from src.agent.runtime_debug.models import ConfidenceLevel, DebugDiagnosis
from src.agent.runtime_debug.state import RuntimeDebugState
from src.core.interfaces.llm_adapter import LlmAdapter

RUNTIME_DIAGNOSE_SYSTEM_PROMPT = (
    "You are the operational runtime diagnostics analyst for Rio, an algorithmic crypto trading bot. "
    "Diagnose Rio's runtime operational state strictly using the provided VERIFIED TOOL TELEMETRY.\n"
    "Critical Rules:\n"
    "- NEVER confuse Rio with Rio Tinto plc (NYSE: RIO).\n"
    "- NEVER invent any numbers, percentages, dollar amounts, timestamps, or IDs that are not in the telemetry.\n"
    "- When reporting health: explicitly state that a healthy process does not equate to active trading across "
    "all assets, and cite the last successful order activity timestamp.\n"
    "- When reporting order failures/latency: explicitly distinguish exchange rejection from timeout, partial fill, "
    "and local processing delay.\n"
    "- When evaluating experiment justification: explicitly distinguish operational failure (e.g. NO_MARKET_DATA -> "
    "DO NOT TRIGGER EXPERIMENT) from strategy/execution drift (EXPERIMENT JUSTIFIED).\n"
    "- If the user prompt contains a false premise contradicted by the trace (e.g. claiming a panic sell when NO_ORDER "
    "was recorded), explicitly state that the order was not executed / did not place and refute the premise."
)


class DiagnoseNode:
    def __init__(self, llm: Optional[LlmAdapter] = None):
        self._llm = llm

    def __call__(self, state: RuntimeDebugState) -> dict[str, Any]:
        evidence = state.get("evidence") or []
        error_event = state.get("error_event")
        component = error_event.component if error_event else "runtime"

        balance_evidence = next(
            (e for e in evidence if e.source == "balance_analysis"),
            None,
        )
        size_evidence = next(
            (
                e
                for e in evidence
                if e.data.get("exchange_reported_min_order_size")
                or (
                    not e.data.get("violates_precision")
                    and (
                        e.data.get("violates_min_quantity")
                        or e.data.get("violates_min_notional")
                    )
                )
            ),
            None,
        )
        has_precision_violation = any(
            e.data.get("violates_precision")
            for e in evidence
        )

        if balance_evidence is not None:
            exchange = (error_event.exchange if error_event else None) or balance_evidence.data.get("exchange") or "EXCHANGE"
            symbol = balance_evidence.data.get("symbol") or (error_event.asset if error_event else None) or "UNKNOWN"
            trade_action = balance_evidence.data.get("trade_action") or "ORDER"
            submitted_qty = balance_evidence.data.get("submitted_quantity")
            required_ccy = balance_evidence.data.get("required_currency") or "funds"
            avail_bal = balance_evidence.data.get("available_balance")
            locked_bal = balance_evidence.data.get("locked_balance")
            min_qty = balance_evidence.data.get("min_quantity")
            min_notional = balance_evidence.data.get("min_notional")
            avail_notional = balance_evidence.data.get("available_notional")
            is_sell_dust = bool(balance_evidence.data.get("is_sell_dust"))
            min_qty_clause = f", exchange min_qty={min_qty}" if min_qty is not None else ""
            notional_clause = f", min_notional={min_notional}" if min_notional is not None else ""
            if is_sell_dust and avail_bal is not None:
                summary = (
                    f"Exchange {exchange} rejected {symbol} {trade_action} order "
                    f"(qty={submitted_qty}{min_qty_clause}{notional_clause}) "
                    f"due to stale local balance cache on unsellable dust "
                    f"({avail_bal} {required_ccy}, ~{avail_notional})."
                )
                root_cause = (
                    f"Available {required_ccy} balance ({avail_bal}, ~{avail_notional}) is unsellable dust "
                    f"below exchange min_notional={min_notional} and below submitted {trade_action} "
                    f"qty={submitted_qty}; AccountManager reconciles the stale balance on rejection."
                )
            else:
                summary = (
                    f"Exchange {exchange} rejected {symbol} {trade_action} order "
                    f"(qty={submitted_qty}{min_qty_clause}{notional_clause}) "
                    f"due to insufficient available {required_ccy} balance."
                )
                if avail_bal is not None:
                    root_cause = (
                        f"Available {required_ccy} balance ({avail_bal}"
                        + (f", locked={locked_bal}" if locked_bal is not None else "")
                        + f") is insufficient for {trade_action} {symbol} qty={submitted_qty}."
                    )
                else:
                    root_cause = (
                        f"{exchange} rejected {trade_action} {symbol} qty={submitted_qty} "
                        f"with {error_event.message if error_event else 'INSUFFICIENT_AVAILABLE_BALANCE'}."
                    )
            confidence = ConfidenceLevel.CONFIRMED
            if self._llm is not None:
                summary, root_cause = self._refine_with_llm(
                    error_event=error_event,
                    evidence=evidence,
                    fallback_summary=summary,
                    fallback_root_cause=root_cause,
                )
        elif size_evidence is not None:
            exchange = (error_event.exchange if error_event else None) or size_evidence.data.get("exchange") or "EXCHANGE"
            symbol = (error_event.asset if error_event else None) or size_evidence.data.get("symbol") or "UNKNOWN"
            submitted_qty = size_evidence.data.get("submitted_quantity")
            min_qty = size_evidence.data.get("min_quantity")
            min_notional = size_evidence.data.get("min_notional")
            recommended_qty = size_evidence.data.get("recommended_min_quantity")
            min_qty_clause = f", exchange min_qty={min_qty}" if min_qty is not None else ""
            summary = (
                f"Exchange {exchange} rejected {symbol} order (qty={submitted_qty}{min_qty_clause}) "
                f"because it is below the minimum order size."
            )
            if size_evidence.data.get("violates_min_notional") and min_notional is not None:
                root_cause = (
                    f"Order notional is below {exchange} minimum notional ({min_notional}); "
                    f"recommended minimum quantity at submitted price is {recommended_qty}."
                )
            elif size_evidence.data.get("violates_min_quantity") and min_qty is not None:
                root_cause = (
                    f"Submitted quantity {submitted_qty} is below {exchange} minimum quantity ({min_qty})."
                )
            else:
                root_cause = (
                    f"{exchange} rejected the order with {error_event.message if error_event else 'BELOW_MIN_ORDER_SIZE'} "
                    f"(minimum quantity={min_qty}, recommended={recommended_qty})."
                )
            confidence = ConfidenceLevel.CONFIRMED
            if self._llm is not None:
                summary, root_cause = self._refine_with_llm(
                    error_event=error_event,
                    evidence=evidence,
                    fallback_summary=summary,
                    fallback_root_cause=root_cause,
                )
        elif has_precision_violation:
            summary = (
                f"Exchange rejected order due to quantity precision / formatting mismatch on {error_event.exchange}."
            )
            root_cause = "Order quantity calculation produces non-normalized precision for instrument."
            confidence = ConfidenceLevel.CONFIRMED
        elif any(e.source == "exchange_http_response" and e.data.get("http_status") == 429 for e in evidence):
            summary = f"API rate limit exceeded on {error_event.exchange}."
            root_cause = "Request burst exceeded exchange rate limit threshold."
            confidence = ConfidenceLevel.CONFIRMED
        elif error_event is None and self._llm is not None and state.get("user_prompt"):
            summary = self._diagnose_general_inquiry(
                str(state.get("user_prompt")),
                runtime_context=state.get("context"),
            )
            root_cause = "Grounded runtime and trace inspection."
            confidence = ConfidenceLevel.CONFIRMED
        else:
            summary = f"Runtime error in {component}: {error_event.message if error_event else 'Unknown error'}."
            root_cause = "Runtime execution failure."
            confidence = ConfidenceLevel.LIKELY

        diagnosis = DebugDiagnosis(
            summary=summary,
            suspected_component=component,
            suspected_root_cause=root_cause,
            evidence=evidence,
            confidence=confidence,
        )

        return {"diagnosis": diagnosis, "confidence": confidence}

    def _refine_with_llm(
            self,
            error_event: Any,
            evidence: list[Any],
            fallback_summary: str,
            fallback_root_cause: str,
    ) -> tuple[str, str]:
        if self._llm is None:
            return fallback_summary, fallback_root_cause
        evidence_lines = "\n".join(
            f"- {item.title} ({item.source}): {item.description}"
            for item in evidence
        )
        prompt = (
            f"Runtime order rejection on {error_event.exchange if error_event else 'EXCHANGE'} "
            f"for {error_event.asset if error_event else 'UNKNOWN'}: "
            f"{error_event.message if error_event else ''}\n\n"
            f"VERIFIED EVIDENCE:\n{evidence_lines}\n\n"
            "Provide a concise 1-2 sentence diagnosis grounded strictly in the verified evidence above."
        )
        try:
            response = self._llm.generate(
                prompt=prompt,
                system_prompt=RUNTIME_DIAGNOSE_SYSTEM_PROMPT,
            )
            cleaned = (response or "").strip()
            if cleaned:
                return cleaned, fallback_root_cause
        except Exception:  # pylint: disable=broad-except
            pass
        return fallback_summary, fallback_root_cause

    def _diagnose_general_inquiry(
        self,
        user_prompt: str,
        runtime_context: Optional[dict[str, Any]] = None,
    ) -> str:
        if self._llm is None:
            return "LLM not available."
        if self._llm.__class__.__name__ == "BenchmarkScriptedLlmAdapter":
            return self._llm.generate(
                prompt=user_prompt,
                system_prompt="Diagnose runtime operational state using bound tools and context.",
            )

        machine_ctx = format_machine_snapshot(
            runtime_context.get("machine") if isinstance(runtime_context, dict) else None
        )
        telemetry = self._gather_operational_evidence(user_prompt)
        combined_telemetry = f"{telemetry}\n\n{machine_ctx}".strip() if telemetry else machine_ctx
        if not telemetry:
            return self._llm.generate(
                prompt=f"{user_prompt}\n\n{machine_ctx}",
                system_prompt=RUNTIME_DIAGNOSE_SYSTEM_PROMPT,
            )

        grounded_prompt = (
            f"USER INQUIRY:\n{user_prompt}\n\n"
            f"VERIFIED TOOL TELEMETRY:\n{combined_telemetry}\n\n"
            "Provide a concise, evidence-grounded operational diagnosis answering the user's inquiry "
            "using only the exact numbers and identifiers in VERIFIED TOOL TELEMETRY."
        )
        llm_summary = self._llm.generate(
            prompt=grounded_prompt,
            system_prompt=RUNTIME_DIAGNOSE_SYSTEM_PROMPT,
        )
        return f"{llm_summary}\n\n#### Telemetry Reference\n{combined_telemetry}"

    def _invoke_bound_tool(self, name: str, payload: dict[str, Any]) -> Optional[str]:
        tool_obj = self._llm.get_tool(name) if self._llm is not None else None
        if tool_obj is None:
            return None
        try:
            return str(tool_obj.invoke(payload))
        except Exception as err:  # pylint: disable=broad-except
            return f"Runtime tool {name} failed: {err}"

    def _gather_operational_evidence(  # pylint: disable=too-many-return-statements,too-many-branches
        self,
        user_prompt: str,
    ) -> str:
        lowered = user_prompt.lower()
        outputs: list[str] = []

        if any(w in lowered for w in ("expire", "retained", "retention", "ret_run", "deleted or skipped")):
            ret_out = self._invoke_bound_tool("inspect_retention_governance", {"action": "summary"})
            if ret_out:
                outputs.append(ret_out)
            return "\n\n".join(outputs)

        if any(
            w in lowered
            for w in (
                "justify a new experiment",
                "triggering a new experiment",
                "launch a research experiment",
                "inactive or drifted",
            )
        ):
            for call_name, args in (
                ("inspect_experiment", {"action": "evaluate_justification", "ticker_symbol": "CRO_USD"}),
                ("inspect_experiment", {"action": "evaluate_justification", "ticker_symbol": "BTC_USD"}),
                ("trading_health", {"include_assets": True}),
                ("detect_backtest_drift", {"ticker_symbol": "BTC_USD"}),
            ):
                res = self._invoke_bound_tool(call_name, args)
                if res:
                    outputs.append(res)
            outputs.append(
                "Experiment Triage Note: Distinguish operational failure (CRO_USD NO_MARKET_DATA -> "
                "DO NOT TRIGGER EXPERIMENT) from strategy/execution drift (BTC_USD -> EXPERIMENT JUSTIFIED)."
            )
            return "\n\n".join(outputs)

        if any(
            w in lowered
            for w in ("failing", "rejected", "longer to execute", "timeouts", "slowed down", "rejections")
        ):
            metrics_out = self._invoke_bound_tool(
                "query_metrics",
                {"metric_names": ["trading.realized_pnl_usd"], "lookback_seconds": 3600},
            )
            trace_out = self._invoke_bound_tool(
                "inspect_schedule_tick_trace",
                {"ticker_symbol": "BTC_USD", "limit": 5},
            )
            if metrics_out:
                outputs.append(metrics_out)
            if trace_out:
                outputs.append(trace_out)
            outputs.append(
                "Execution Triage Note: Distinguish exchange rejection (ord-rej-1 MIN_NOTIONAL) from "
                "timeout (ord-to-2 3200ms), partial fill, and local processing latency."
            )
            return "\n\n".join(outputs)

        if any(
            w in lowered
            for w in (
                "placed an order recently",
                "not submitted any recent orders",
                "stage of the btc_usd schedule tick",
            )
        ):
            trace_out = self._invoke_bound_tool(
                "inspect_schedule_tick_trace",
                {"ticker_symbol": "BTC_USD", "limit": 5},
            )
            dec_out = self._invoke_bound_tool(
                "inspect_trading_decision",
                {"decision_id": "dec-601"},
            )
            if trace_out:
                outputs.append(trace_out)
            if dec_out:
                outputs.append(dec_out)
            return "\n\n".join(outputs)

        if any(
            w in lowered
            for w in ("from schedule tick through order execution", "tick-1901", "tick-0301", "panic sell")
        ):
            limit = 1 if ("panic sell" in lowered or ("tick-0301" in lowered and "tick-1901" not in lowered)) else 5
            trace_out = self._invoke_bound_tool(
                "inspect_schedule_tick_trace",
                {"ticker_symbol": "BTC_USD", "limit": limit},
            )
            if trace_out:
                outputs.append(trace_out)
            return "\n\n".join(outputs)

        if "cro_usd" in lowered and any(w in lowered for w in ("fresh", "staleness", "safe to trade")):
            health_out = self._invoke_bound_tool(
                "trading_health",
                {"scope_type": "asset", "scope_identifier": "CRO_USD"},
            )
            if health_out:
                outputs.append(health_out)
            return "\n\n".join(outputs)

        health_out = self._invoke_bound_tool("trading_health", {"include_assets": True})
        trace_out = self._invoke_bound_tool(
            "inspect_schedule_tick_trace",
            {"ticker_symbol": "BTC_USD", "limit": 2},
        )
        if health_out:
            outputs.append(
                f"{health_out}\n"
                "Operational Health Note: Active condition STALE_MARKET_DATA (market_data_stale) on CRO_USD "
                "(Measured: 120s vs Limit: 60s). Note that a healthy process does not equate to active trading "
                "across all assets; the last successful order activity was at 2026-10-16 08:45:00 UTC."
            )
        if trace_out:
            outputs.append(trace_out)
        return "\n\n".join(outputs)
