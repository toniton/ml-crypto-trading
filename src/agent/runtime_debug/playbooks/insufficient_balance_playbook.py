from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar, Optional

from src.agent.runtime_debug.models import Evidence, RuntimeErrorEvent
from src.agent.runtime_debug.tools import RuntimeDebugToolbox


class InsufficientBalancePlaybook:
    name: str = "insufficient_balance"
    REPEAT_OCCURRENCE_PAUSE_THRESHOLD: ClassVar[int] = 3

    BALANCE_ERROR_CODES: ClassVar[dict[str, set[int | str]]] = {
        "CRYPTO_DOT_COM": {306, 308},
        "BINANCE": {-2010},
        "COINBASE": {"INSUFFICIENT_FUNDS"},
        "KRAKEN": {"EOrder:Insufficient funds"},
    }

    BALANCE_KEYWORDS: ClassVar[set[str]] = {
        "insufficient_available_balance",
        "insufficient available balance",
        "insufficient_balance",
        "insufficient balance",
        "insufficient_funds",
        "insufficient funds",
    }

    def matches(self, event: RuntimeErrorEvent) -> bool:
        provider = (event.exchange or "").upper().strip()
        code = event.exchange_code
        msg = (event.message or "").lower()
        normalized_msg = msg.replace("_", " ")

        if provider in self.BALANCE_ERROR_CODES:
            known_codes = self.BALANCE_ERROR_CODES[provider]
            if code in known_codes or any(str(kc).lower() in msg for kc in known_codes):
                return True

        return any(
            keyword in msg or keyword in normalized_msg
            for keyword in self.BALANCE_KEYWORDS
        )

    @staticmethod
    def _split_symbol(symbol: str) -> tuple[str, str]:
        normalized = symbol.upper().replace("/", "_").replace("-", "_")
        if "_" in normalized:
            base, quote = normalized.split("_", 1)
            return base, quote
        return normalized, "USD"

    @staticmethod
    def _parse_decimal(raw: Any) -> Optional[Decimal]:
        if raw is None or str(raw).strip() == "":
            return None
        try:
            return Decimal(str(raw))
        except InvalidOperation:
            return None

    def investigate(
            self,
            event: RuntimeErrorEvent,
            toolbox: RuntimeDebugToolbox,
    ) -> list[Evidence]:
        evidence_list: list[Evidence] = []
        exchange = (event.exchange or "EXCHANGE").upper()
        symbol = (event.asset or "UNKNOWN").upper().replace("/", "_").replace("-", "_")
        base_ccy, quote_ccy = self._split_symbol(symbol)

        rules = toolbox.get_exchange_instrument_metadata(exchange, symbol)
        min_qty = str(rules.get("min_quantity", "0.0001"))
        min_notional = rules.get("min_notional")
        metadata_source = str(rules.get("source") or "exchange_metadata")
        notional_desc = f", min_notional={min_notional}" if min_notional is not None else ""
        evidence_list.append(
            Evidence(
                title=f"{exchange} Instrument Constraints",
                description=(
                    f"{exchange} instrument metadata for {symbol}: "
                    f"min_quantity={min_qty}, quantity_step={rules.get('quantity_step')}{notional_desc} "
                    f"(source: {metadata_source})."
                ),
                source="exchange_metadata",
                data=rules,
            )
        )

        raw_quantity = event.metadata.get("order_quantity")
        raw_price = event.metadata.get("order_price")
        trade_action = str(event.metadata.get("trade_action") or "").upper()
        if (not raw_quantity or not raw_price or not trade_action) and event.order_id:
            order = toolbox.get_order(event.order_id)
            if order:
                raw_quantity = raw_quantity or str(order.quantity)
                raw_price = raw_price or str(order.price)
                if not trade_action and order.trade_action:
                    trade_action = order.trade_action.value.upper()

        qty_dec = self._parse_decimal(raw_quantity)
        price_dec = self._parse_decimal(raw_price)
        order_notional = (
            qty_dec * price_dec
            if qty_dec is not None and price_dec is not None
            else None
        )
        required_currency = base_ccy if trade_action == "SELL" else quote_ccy
        required_amount = qty_dec if trade_action == "SELL" else order_notional

        balances = toolbox.get_account_balances(exchange)
        balance_entry = next(
            (b for b in balances if b.get("currency") == required_currency),
            None,
        )
        available_dec = (
            self._parse_decimal(balance_entry.get("available"))
            if balance_entry is not None
            else None
        )
        locked_dec = (
            self._parse_decimal(balance_entry.get("locked"))
            if balance_entry is not None
            else None
        )
        open_orders = toolbox.get_open_orders(exchange, symbol)

        min_notional_dec = self._parse_decimal(min_notional)
        min_qty_dec = self._parse_decimal(min_qty) or Decimal("0")
        available_notional = (
            available_dec * price_dec
            if trade_action == "SELL" and available_dec is not None and price_dec is not None
            else None
        )
        is_sell_dust = (
            trade_action == "SELL"
            and available_notional is not None
            and min_notional_dec is not None
            and available_notional < min_notional_dec
        )
        raw_occurrences = event.metadata.get("occurrence_count", 1)
        try:
            occurrence_count = max(1, int(raw_occurrences))
        except (TypeError, ValueError):
            occurrence_count = 1

        recommended_changes: list[dict[str, Any]] = []
        remediation_action = "pause_asset"

        if (
            trade_action == "BUY"
            and available_dec is not None
            and order_notional is not None
            and order_notional > Decimal("0")
            and min_notional_dec is not None
            and available_dec >= min_notional_dec
            and available_dec < order_notional
        ):
            # Available quote balance can still fund smaller orders -> tighten exposure cap
            safe_ratio = (available_dec * Decimal("0.9")) / order_notional
            target_pct = max(Decimal("0.05"), min(Decimal("0.50"), safe_ratio.quantize(Decimal("0.01"))))
            remediation_action = "reduce_exposure"
            recommended_changes.append(
                {
                    "path": f"assets.{symbol}.portfolio.max_exposure_pct",
                    "new_value": float(target_pct),
                    "reason": (
                        f"Available {quote_ccy} balance ({available_dec}) is below submitted BUY notional "
                        f"({order_notional:.4f}) but above exchange min_notional ({min_notional_dec}); "
                        f"reducing max_exposure_pct to {target_pct} keeps orders within available balance."
                    ),
                }
            )
        elif is_sell_dust and occurrence_count < self.REPEAT_OCCURRENCE_PAUSE_THRESHOLD:
            # Single/transient SELL rejection on unsellable dust caused by stale local balance cache.
            # AccountManager already reconciles balances on OrderRejectedEvent; disabling the asset
            # would unnecessarily halt BUY orders too.
            remediation_action = "reconcile_balance_dust"
        else:
            # Repeated/chronic SELL deficit, BUY below min_notional, or live balance unavailable
            recommended_changes.append(
                {
                    "path": f"assets.{symbol}.enabled",
                    "new_value": False,
                    "reason": (
                        f"Pause {symbol} to stop repeated {event.message or 'INSUFFICIENT_AVAILABLE_BALANCE'} "
                        f"rejections (exchange min_quantity={min_qty}{notional_desc})"
                        + (
                            f"; available {required_currency}={available_dec}"
                            + (f", locked={locked_dec}" if locked_dec is not None else "")
                            if available_dec is not None
                            else ""
                        )
                        + "."
                    ),
                }
            )

        balance_desc = (
            f"Available {required_currency}={available_dec}, locked={locked_dec}"
            if available_dec is not None
            else f"Live {required_currency} balance unavailable"
        )
        dust_note = (
            f" Remaining {available_dec} {required_currency} (~{available_notional:.4f} {quote_ccy}) "
            f"is unsellable dust below exchange min_notional={min_notional_dec}; "
            f"balance reconciliation on order rejection refreshes local cache."
            if is_sell_dust and available_notional is not None
            else ""
        )
        evidence_list.append(
            Evidence(
                title="Insufficient Balance Analysis",
                description=(
                    f"{exchange} rejected {trade_action or 'ORDER'} {symbol} qty={raw_quantity} "
                    f"(notional={f'{order_notional:.4f}' if order_notional is not None else 'unknown'}) "
                    f"with {event.message} (code {event.exchange_code}). "
                    f"{balance_desc}; open_orders={len(open_orders)}; "
                    f"exchange min_quantity={min_qty}{notional_desc}.{dust_note}"
                ),
                source="balance_analysis",
                data={
                    "exchange": exchange,
                    "symbol": symbol,
                    "trade_action": trade_action or None,
                    "submitted_quantity": str(raw_quantity) if raw_quantity is not None else None,
                    "submitted_price": str(raw_price) if raw_price is not None else None,
                    "submitted_notional": str(order_notional) if order_notional is not None else None,
                    "required_currency": required_currency,
                    "required_amount": str(required_amount) if required_amount is not None else None,
                    "available_balance": str(available_dec) if available_dec is not None else None,
                    "available_notional": f"{available_notional:.4f}" if available_notional is not None else None,
                    "locked_balance": str(locked_dec) if locked_dec is not None else None,
                    "open_orders_count": len(open_orders),
                    "min_quantity": str(min_qty_dec),
                    "min_notional": str(min_notional_dec) if min_notional_dec is not None else None,
                    "metadata_source": metadata_source,
                    "is_sell_dust": is_sell_dust,
                    "occurrence_count": occurrence_count,
                    "remediation_action": remediation_action,
                    "proposed_changes": recommended_changes,
                },
            )
        )

        return evidence_list
