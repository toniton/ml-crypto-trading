from __future__ import annotations

from typing import Any, Optional

from src.agent.runtime_debug.models import DebugSuggestion, RiskLevel
from src.agent.runtime_debug.state import RuntimeDebugState
from src.core.interfaces.llm_adapter import LlmAdapter


class GenerateSuggestionNode:
    def __init__(self, llm: Optional[LlmAdapter] = None):
        self._llm = llm

    def __call__(self, state: RuntimeDebugState) -> dict[str, Any]:
        diagnosis = state.get("diagnosis")
        evidence = state.get("evidence") or []
        error_event = state.get("error_event")

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
            symbol = (
                balance_evidence.data.get("symbol")
                or (error_event.asset if error_event else None)
                or "UNKNOWN"
            )
            exchange = (
                (error_event.exchange if error_event else None)
                or balance_evidence.data.get("exchange")
                or "EXCHANGE"
            )
            min_qty = balance_evidence.data.get("min_quantity")
            min_notional = balance_evidence.data.get("min_notional")
            remediation_action = balance_evidence.data.get("remediation_action")
            proposed_changes = balance_evidence.data.get("proposed_changes") or []
            primary_change = proposed_changes[0] if proposed_changes else None
            min_qty_clause = f" (exchange min_qty={min_qty}" + (
                f", min_notional={min_notional})" if min_notional is not None else ")"
            ) if min_qty is not None else ""

            if remediation_action == "reconcile_balance_dust" and not proposed_changes:
                avail_bal = balance_evidence.data.get("available_balance")
                avail_notional = balance_evidence.data.get("available_notional")
                required_ccy = balance_evidence.data.get("required_currency") or "base asset"
                summary = (
                    f"No config change needed for {symbol}{min_qty_clause}: remaining "
                    f"{avail_bal} {required_ccy} (~{avail_notional}) is unsellable dust on {exchange}."
                )
                proposed_change = (
                    f"No configuration change required. AccountManager automatically reconciles "
                    f"{exchange} balances on order rejection so TradingExecutor skips further "
                    f"sub-balance SELLs until a future BUY brings {symbol} above min_notional={min_notional}."
                )
                rationale = (
                    f"Available {required_ccy} ({avail_bal}, ~{avail_notional}) is below {exchange} "
                    f"min_notional={min_notional} (unsellable dust) while still meeting min_qty={min_qty}. "
                    f"Disabling assets.{symbol}.enabled on a transient stale-balance SELL would unnecessarily "
                    f"halt BUY orders; automatic balance reconciliation resolves the cache drift."
                )
                if self._llm is not None:
                    rationale = self._refine_rationale_with_llm(
                        symbol=symbol,
                        exchange=exchange,
                        proposed_change=proposed_change,
                        fallback_rationale=rationale,
                        evidence=evidence,
                    )
                suggestion = DebugSuggestion(
                    summary=summary,
                    root_cause=(
                        diagnosis.suspected_root_cause
                        if diagnosis
                        else f"Unsellable {symbol} dust with stale local balance on {exchange}."
                    ),
                    affected_component="trading.accounts.account_manager",
                    proposed_change=proposed_change,
                    rationale=rationale,
                    evidence=evidence,
                    risk=RiskLevel.LOW,
                    requires_code_change=False,
                    requires_configuration_change=False,
                    requires_restart=False,
                    requires_manual_validation=False,
                )
            else:
                target_path = (
                    str(primary_change["path"])
                    if isinstance(primary_change, dict) and primary_change.get("path")
                    else f"assets.{symbol}.enabled"
                )
                target_value = (
                    primary_change["new_value"]
                    if isinstance(primary_change, dict) and "new_value" in primary_change
                    else False
                )

                if target_path.endswith(".enabled") and target_value is False:
                    summary = f"Pause {symbol} (set {target_path}=false){min_qty_clause} due to insufficient balance on {exchange}."
                    proposed_change = (
                        f"Set {target_path} to false to stop repeated INSUFFICIENT_AVAILABLE_BALANCE "
                        f"rejections until {symbol} balances are reconciled or replenished."
                    )
                else:
                    summary = f"Update {target_path} to {target_value}{min_qty_clause} to fit available balance on {exchange}."
                    proposed_change = (
                        f"Update {target_path} to {target_value} so {symbol} orders fit within "
                        f"available {exchange} balance."
                    )

                rationale = (
                    str(primary_change.get("reason"))
                    if isinstance(primary_change, dict) and primary_change.get("reason")
                    else balance_evidence.description
                )
                if self._llm is not None:
                    rationale = self._refine_rationale_with_llm(
                        symbol=symbol,
                        exchange=exchange,
                        proposed_change=proposed_change,
                        fallback_rationale=rationale,
                        evidence=evidence,
                    )
                suggestion = DebugSuggestion(
                    summary=summary,
                    root_cause=(
                        diagnosis.suspected_root_cause
                        if diagnosis
                        else f"Insufficient available balance for {symbol} on {exchange}."
                    ),
                    affected_component=target_path,
                    proposed_change=proposed_change,
                    rationale=rationale,
                    evidence=evidence,
                    risk=RiskLevel.MEDIUM,
                    requires_code_change=False,
                    requires_configuration_change=True,
                    requires_restart=False,
                    requires_manual_validation=True,
                )
        elif size_evidence is not None:
            symbol = (
                (error_event.asset if error_event else None)
                or size_evidence.data.get("symbol")
                or "UNKNOWN"
            )
            exchange = (
                (error_event.exchange if error_event else None)
                or size_evidence.data.get("exchange")
                or "EXCHANGE"
            )
            recommended_qty = (
                size_evidence.data.get("recommended_min_quantity")
                or size_evidence.data.get("min_quantity")
            )
            min_qty = size_evidence.data.get("min_quantity")
            min_notional = size_evidence.data.get("min_notional")
            submitted_qty = size_evidence.data.get("submitted_quantity")
            metadata_source = size_evidence.data.get("metadata_source", "exchange_api")

            proposed_change = (
                f"Update assets.{symbol}.min_quantity to {recommended_qty} "
                f"to satisfy {exchange} minimum order size requirements."
            )
            rationale = (
                f"{exchange} rejected order qty={submitted_qty} with "
                f"{error_event.message if error_event else 'BELOW_MIN_ORDER_SIZE'}. "
                f"Exchange metadata ({metadata_source}) reports min_quantity={min_qty}"
                + (f", min_notional={min_notional}" if min_notional is not None else "")
                + f"; raising assets.{symbol}.min_quantity to {recommended_qty} prevents sub-minimum rejections."
            )
            if self._llm is not None:
                rationale = self._refine_rationale_with_llm(
                    symbol=symbol,
                    exchange=exchange,
                    proposed_change=proposed_change,
                    fallback_rationale=rationale,
                    evidence=evidence,
                )
            min_qty_note = f" (exchange min_qty={min_qty})" if min_qty is not None else ""
            suggestion = DebugSuggestion(
                summary=f"Raise assets.{symbol}.min_quantity to {recommended_qty}{min_qty_note} for {exchange}.",
                root_cause=(
                    diagnosis.suspected_root_cause
                    if diagnosis
                    else f"Order size for {symbol} is below {exchange} minimum order size."
                ),
                affected_component=f"assets.{symbol}.min_quantity",
                proposed_change=proposed_change,
                rationale=rationale,
                evidence=evidence,
                risk=RiskLevel.MEDIUM,
                requires_code_change=False,
                requires_configuration_change=True,
                requires_restart=False,
                requires_manual_validation=True,
            )
        elif has_precision_violation:
            suggestion = DebugSuggestion(
                summary="Normalize and quantize order quantity according to exchange instrument rules.",
                root_cause="Calculated order quantity does not conform to required decimal precision / step size.",
                affected_component="trading.orders.quantity_normalization",
                proposed_change=(
                    "Apply instrument decimal rounding to order quantity (e.g. quantize to instrument precision) "
                    "before submitting order to exchange."
                ),
                rationale="Exchange rejects non-conforming quantities deterministically with error 213.",
                evidence=evidence,
                risk=RiskLevel.HIGH,
                requires_code_change=True,
                requires_configuration_change=False,
                requires_restart=False,
                requires_manual_validation=True,
            )
        elif any(e.source == "exchange_http_response" and e.data.get("http_status") == 429 for e in evidence):
            suggestion = DebugSuggestion(
                summary="Enable exponential backoff and rate limit throttling on REST client.",
                root_cause="Request frequency exceeded exchange limits.",
                affected_component="exchange.clients.rest_client",
                proposed_change="Add retry-after delay handling and reduce polling frequency.",
                rationale="Prevents temporary account lockouts and dropped orders.",
                evidence=evidence,
                risk=RiskLevel.MEDIUM,
                requires_code_change=False,
                requires_configuration_change=True,
                requires_restart=False,
                requires_manual_validation=False,
            )
        else:
            summary = diagnosis.summary if diagnosis else "Investigate runtime failure"
            suggestion = DebugSuggestion(
                summary=summary,
                root_cause=diagnosis.suspected_root_cause if diagnosis else "Unknown",
                affected_component=diagnosis.suspected_component if diagnosis else "system",
                proposed_change="Review error stack trace and component state.",
                rationale="Manual review recommended for unclassified error.",
                evidence=evidence,
                risk=RiskLevel.HIGH,
                requires_code_change=True,
                requires_configuration_change=False,
                requires_restart=False,
                requires_manual_validation=True,
            )

        return {"suggestion": suggestion}

    def _refine_rationale_with_llm(
            self,
            symbol: str,
            exchange: str,
            proposed_change: str,
            fallback_rationale: str,
            evidence: list[Any],
    ) -> str:
        if self._llm is None:
            return fallback_rationale
        evidence_lines = "\n".join(
            f"- {item.title} ({item.source}): {item.description}"
            for item in evidence
        )
        prompt = (
            f"Proposed configuration change for {symbol} on {exchange}: {proposed_change}\n\n"
            f"VERIFIED EVIDENCE:\n{evidence_lines}\n\n"
            "Write a concise 1-2 sentence rationale grounded strictly in the verified evidence."
        )
        try:
            response = self._llm.generate(
                prompt=prompt,
                system_prompt="You are a concise trading bot remediation advisor. Use only verified telemetry.",
            )
            cleaned = (response or "").strip()
            if cleaned:
                return cleaned
        except Exception:  # pylint: disable=broad-except
            pass
        return fallback_rationale
