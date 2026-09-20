from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

from src.agent.runtime_debug.models import Evidence, RuntimeErrorEvent
from src.agent.runtime_debug.tools import RuntimeDebugToolbox


class OrderValidationPlaybook:
    name: str = "order_validation"

    KNOWN_EXCHANGE_ERROR_CODES: ClassVar[dict[str, set[int | str]]] = {
        "CRYPTO_DOT_COM": {213, 204, 308},
        "BINANCE": {-1013, -1111, -1010, -2010},
        "COINBASE": {"INVALID_ORDER_SIZE", "INSUFFICIENT_FUNDS", "INVALID_PRICE_STEP"},
        "BYBIT": {10001, 170131, 170132, 170137},
        "KRAKEN": {"EOrder:Order minimum not met", "EOrder:Invalid price"},
        "OKX": {51000, 51001, 51006},
    }

    VALIDATION_KEYWORDS: ClassVar[set[str]] = {
        "invalid quantity",
        "precision",
        "lot size",
        "step size",
        "min_quantity",
        "max_quantity",
        "tick size",
        "invalid price",
        "order size",
        "filter failure",
    }

    def matches(self, event: RuntimeErrorEvent) -> bool:
        provider = (event.exchange or "").upper().strip()
        code = event.exchange_code
        msg = (event.message or "").lower()

        if provider in self.KNOWN_EXCHANGE_ERROR_CODES:
            known_codes = self.KNOWN_EXCHANGE_ERROR_CODES[provider]
            if code in known_codes or any(str(kc).lower() in msg for kc in known_codes):
                return True

        if any(keyword in msg for keyword in self.VALIDATION_KEYWORDS):
            return True

        operation = (event.operation or "").lower()
        if event.http_status == 400 and operation in ("execute_order", "place_order", "create_order"):
            return True

        return False

    def investigate(self, event: RuntimeErrorEvent, toolbox: RuntimeDebugToolbox) -> list[Evidence]:
        evidence_list: list[Evidence] = []
        exchange = (event.exchange or "EXCHANGE").upper()
        symbol = event.asset or "UNKNOWN"

        # 1. Exchange Rule Evidence
        rules = toolbox.get_exchange_instrument_metadata(exchange, symbol)
        max_precision = rules.get("quantity_precision", 4)
        min_qty = Decimal(str(rules.get("min_quantity", "0.0001")))
        step_size = Decimal(str(rules.get("quantity_step", "0.0001")))

        evidence_list.append(
            Evidence(
                title=f"{exchange} Instrument Constraints",
                description=(
                    f"{exchange} requires {symbol} order quantities to have at most "
                    f"{max_precision} decimal places, minimum quantity of {min_qty}, "
                    f"and lot increment of {step_size}."
                ),
                source="exchange_metadata",
                data=rules,
            )
        )

        # 2. Submitted Order Quantity & Precision Validation
        raw_quantity = event.metadata.get("order_quantity")
        if not raw_quantity and event.order_id:
            order = toolbox.get_order(event.order_id)
            if order:
                raw_quantity = str(order.quantity)

        if raw_quantity:
            try:
                qty_dec = Decimal(raw_quantity)
                dec_places = abs(qty_dec.as_tuple().exponent) if "." in raw_quantity else 0
                is_precision_violating = dec_places > max_precision
                is_under_min = qty_dec < min_qty

                violation_details = []
                if is_precision_violating:
                    violation_details.append(
                        f"Quantity has {dec_places} decimals exceeding maximum allowed {max_precision} decimals"
                    )
                if is_under_min:
                    violation_details.append(
                        f"Quantity {qty_dec} is below minimum allowed order quantity {min_qty}"
                    )

                evidence_list.append(
                    Evidence(
                        title="Quantity Validation Failure",
                        description=(
                                f"Submitted order quantity '{raw_quantity}' violates {exchange} rules: "
                                + ("; ".join(violation_details) if violation_details else "format invalid")
                        ),
                        source="order_validation_analysis",
                        data={
                            "exchange": exchange,
                            "submitted_quantity": raw_quantity,
                            "actual_decimals": dec_places,
                            "allowed_precision": max_precision,
                            "violates_precision": is_precision_violating,
                            "violates_min_quantity": is_under_min,
                        },
                    )
                )
            except Exception:
                evidence_list.append(
                    Evidence(
                        title="Submitted Order Quantity",
                        description=f"Submitted order quantity is '{raw_quantity}'.",
                        source="order_metadata",
                        data={"submitted_quantity": raw_quantity},
                    )
                )

        # 3. Last Successful Order Commit Diff
        last_success_commit = toolbox.get_last_successful_order_commit(symbol)
        if last_success_commit and event.commit_hash and last_success_commit != event.commit_hash:
            diff = toolbox.get_configuration_diff(last_success_commit, event.commit_hash)
            evidence_list.append(
                Evidence(
                    title="VCS Configuration Comparison",
                    description=(
                        f"Orders for {symbol} on {exchange} previously succeeded under commit {last_success_commit[:8]}. "
                        f"Failure occurred under commit {event.commit_hash[:8]}."
                    ),
                    source="vcs_history",
                    data={
                        "last_successful_commit": last_success_commit,
                        "current_failing_commit": event.commit_hash,
                        "diff": diff,
                    },
                )
            )

        return evidence_list
