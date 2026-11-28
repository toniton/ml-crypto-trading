from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
from typing import ClassVar, Optional

from src.agent.runtime_debug.models import Evidence, RuntimeErrorEvent
from src.agent.runtime_debug.tools import RuntimeDebugToolbox


class OrderValidationPlaybook:
    name: str = "order_validation"

    KNOWN_EXCHANGE_ERROR_CODES: ClassVar[dict[str, set[int | str]]] = {
        "CRYPTO_DOT_COM": {213, 204, 415},
        "BINANCE": {-1013, -1111, -1010},
        "COINBASE": {"INVALID_ORDER_SIZE", "INVALID_PRICE_STEP"},
        "BYBIT": {10001, 170131, 170132, 170137},
        "KRAKEN": {"EOrder:Order minimum not met", "EOrder:Invalid price"},
        "OKX": {51000, 51001, 51006},
    }

    EXCLUDED_BALANCE_CODES: ClassVar[dict[str, set[int | str]]] = {
        "CRYPTO_DOT_COM": {306, 308},
        "BINANCE": {-2010},
        "COINBASE": {"INSUFFICIENT_FUNDS"},
    }

    EXCLUDED_BALANCE_KEYWORDS: ClassVar[set[str]] = {
        "insufficient_available_balance",
        "insufficient available balance",
        "insufficient_balance",
        "insufficient balance",
        "insufficient_funds",
        "insufficient funds",
    }

    MIN_ORDER_SIZE_CODES: ClassVar[dict[str, set[int | str]]] = {
        "CRYPTO_DOT_COM": {415},
    }

    MIN_ORDER_SIZE_KEYWORDS: ClassVar[set[str]] = {
        "below_min_order_size",
        "below min order size",
        "min_order_size",
        "min order size",
        "min_notional",
        "min notional",
        "order minimum not met",
        "min_quantity",
        "min quantity",
    }

    VALIDATION_KEYWORDS: ClassVar[set[str]] = {
        "invalid quantity",
        "precision",
        "lot size",
        "step size",
        "min_quantity",
        "min quantity",
        "max_quantity",
        "max quantity",
        "tick size",
        "invalid price",
        "order size",
        "below_min_order_size",
        "min_order_size",
        "min_notional",
        "filter failure",
    }

    def matches(self, event: RuntimeErrorEvent) -> bool:
        provider = (event.exchange or "").upper().strip()
        code = event.exchange_code
        msg = (event.message or "").lower()
        normalized_msg = msg.replace("_", " ")

        if provider in self.EXCLUDED_BALANCE_CODES and code in self.EXCLUDED_BALANCE_CODES[provider]:
            return False
        if any(kw in msg or kw in normalized_msg for kw in self.EXCLUDED_BALANCE_KEYWORDS):
            return False

        if provider in self.KNOWN_EXCHANGE_ERROR_CODES:
            known_codes = self.KNOWN_EXCHANGE_ERROR_CODES[provider]
            if code in known_codes or any(str(kc).lower() in msg for kc in known_codes):
                return True

        if any(
            keyword in msg or keyword in normalized_msg
            for keyword in self.VALIDATION_KEYWORDS
        ):
            return True

        operation = (event.operation or "").lower()
        if operation in ("execute_order", "place_order", "create_order") and (
            event.http_status == 400 or event.exchange_code is not None
        ):
            return True

        return False

    def _is_exchange_min_order_size_error(self, event: RuntimeErrorEvent) -> bool:
        provider = (event.exchange or "").upper().strip()
        code = event.exchange_code
        msg = (event.message or "").lower()
        normalized_msg = msg.replace("_", " ")

        if provider in self.MIN_ORDER_SIZE_CODES and code in self.MIN_ORDER_SIZE_CODES[provider]:
            return True
        return any(
            kw in msg or kw in normalized_msg
            for kw in self.MIN_ORDER_SIZE_KEYWORDS
        )

    @staticmethod
    def _compute_recommended_min_quantity(
            min_qty: Decimal,
            step_size: Decimal,
            min_notional: Optional[Decimal],
            price_dec: Optional[Decimal],
            submitted_qty: Optional[Decimal] = None,
            exchange_reported_min_size: bool = False,
    ) -> Decimal:
        recommended = min_qty
        if min_notional is not None and price_dec is not None and price_dec > Decimal("0"):
            raw_qty = min_notional / price_dec
            if step_size > Decimal("0"):
                steps = (raw_qty / step_size).to_integral_value(rounding=ROUND_CEILING)
                notional_qty = steps * step_size
            else:
                notional_qty = raw_qty
            if notional_qty > recommended:
                recommended = notional_qty
        if exchange_reported_min_size and submitted_qty is not None and recommended <= submitted_qty:
            increment = step_size if step_size > Decimal("0") else Decimal("1")
            recommended = submitted_qty + increment
        return recommended

    def investigate(self, event: RuntimeErrorEvent, toolbox: RuntimeDebugToolbox) -> list[Evidence]:
        evidence_list: list[Evidence] = []
        exchange = (event.exchange or "EXCHANGE").upper()
        symbol = event.asset or "UNKNOWN"

        rules = toolbox.get_exchange_instrument_metadata(exchange, symbol)
        max_precision = int(rules.get("quantity_precision", 4))
        min_qty = Decimal(str(rules.get("min_quantity", "0.0001")))
        step_size = Decimal(str(rules.get("quantity_step", "0.0001")))
        raw_min_notional = rules.get("min_notional")
        min_notional = (
            Decimal(str(raw_min_notional))
            if raw_min_notional is not None
            else None
        )
        metadata_source = str(rules.get("source") or "exchange_metadata")

        notional_desc = (
            f", and minimum notional of {min_notional}"
            if min_notional is not None
            else ""
        )
        evidence_list.append(
            Evidence(
                title=f"{exchange} Instrument Constraints",
                description=(
                    f"{exchange} requires {symbol} order quantities to have at most "
                    f"{max_precision} decimal places, minimum quantity of {min_qty}, "
                    f"lot increment of {step_size}{notional_desc} "
                    f"(source: {metadata_source})."
                ),
                source="exchange_metadata",
                data=rules,
            )
        )

        raw_quantity = event.metadata.get("order_quantity")
        raw_price = event.metadata.get("order_price")
        if (not raw_quantity or not raw_price) and event.order_id:
            order = toolbox.get_order(event.order_id)
            if order:
                raw_quantity = raw_quantity or str(order.quantity)
                raw_price = raw_price or str(order.price)

        exchange_reported_min_size = self._is_exchange_min_order_size_error(event)

        if raw_quantity:
            try:
                qty_dec = Decimal(str(raw_quantity))
                price_dec = (
                    Decimal(str(raw_price))
                    if raw_price is not None and str(raw_price) != ""
                    else None
                )
                dec_places = abs(qty_dec.as_tuple().exponent) if "." in str(raw_quantity) else 0
                is_precision_violating = dec_places > max_precision
                is_under_min = qty_dec < min_qty
                submitted_notional = (
                    qty_dec * price_dec
                    if price_dec is not None
                    else None
                )
                is_under_min_notional = (
                    min_notional is not None
                    and submitted_notional is not None
                    and submitted_notional < min_notional
                )
                recommended_min_qty = self._compute_recommended_min_quantity(
                    min_qty=min_qty,
                    step_size=step_size,
                    min_notional=min_notional,
                    price_dec=price_dec,
                    submitted_qty=qty_dec,
                    exchange_reported_min_size=exchange_reported_min_size,
                )

                violation_details: list[str] = []
                if is_precision_violating:
                    violation_details.append(
                        f"Quantity has {dec_places} decimals exceeding maximum allowed {max_precision} decimals"
                    )
                if is_under_min:
                    violation_details.append(
                        f"Quantity {qty_dec} is below minimum allowed order quantity {min_qty}"
                    )
                if is_under_min_notional and submitted_notional is not None:
                    violation_details.append(
                        f"Order notional {submitted_notional:.6f} is below minimum notional {min_notional}"
                    )
                if exchange_reported_min_size and not is_under_min and not is_under_min_notional:
                    violation_details.append(
                        f"Exchange rejected order with {event.message} (code {event.exchange_code})"
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
                            "symbol": symbol,
                            "submitted_quantity": str(raw_quantity),
                            "submitted_price": str(raw_price) if raw_price is not None else None,
                            "submitted_notional": str(submitted_notional) if submitted_notional is not None else None,
                            "actual_decimals": dec_places,
                            "allowed_precision": max_precision,
                            "min_quantity": str(min_qty),
                            "min_notional": str(min_notional) if min_notional is not None else None,
                            "recommended_min_quantity": str(recommended_min_qty),
                            "metadata_source": metadata_source,
                            "violates_precision": is_precision_violating,
                            "violates_min_quantity": is_under_min,
                            "violates_min_notional": is_under_min_notional,
                            "exchange_reported_min_order_size": exchange_reported_min_size,
                        },
                    )
                )
            except Exception:
                evidence_list.append(
                    Evidence(
                        title="Submitted Order Quantity",
                        description=f"Submitted order quantity is '{raw_quantity}'.",
                        source="order_metadata",
                        data={"submitted_quantity": str(raw_quantity)},
                    )
                )

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
