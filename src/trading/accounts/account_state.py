from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class CurrencyBalanceState:
    currency: str
    total: Decimal
    available: Decimal
    reserved: Decimal = Decimal("0")
    last_updated_at: float = field(default_factory=time.time)
    version: int = 0
    source: str = "BOOTSTRAP"  # "WS", "REST_RECONCILIATION", "BOOTSTRAP", "EXTERNAL"

    def has_changed(self, other_available: Decimal, other_total: Optional[Decimal] = None) -> bool:
        if self.available != other_available:
            return True
        if other_total is not None and self.total != other_total:
            return True
        return False


@dataclass
class AccountState:
    exchange: str
    account_id: str = "default"
    balances: dict[str, CurrencyBalanceState] = field(default_factory=dict)
    last_reconciliation_time: float = 0.0

    def get_balance(self, currency: str) -> Optional[CurrencyBalanceState]:
        curr_key = currency.upper()
        if curr_key in self.balances:
            return self.balances[curr_key]
        return None

    def update_balance(
            self,
            currency: str,
            available: Decimal,
            total: Optional[Decimal] = None,
            reserved: Optional[Decimal] = None,
            source: str = "WS",
            timestamp: Optional[float] = None,
    ) -> tuple[CurrencyBalanceState, Optional[CurrencyBalanceState]]:
        """Updates or creates a canonical currency balance state.

        Returns: (current_state, previous_state_copy)
        """
        curr_key = currency.upper()
        avail_dec = Decimal(str(available))
        tot_dec = Decimal(str(total)) if total is not None else avail_dec
        res_dec = Decimal(str(reserved)) if reserved is not None else max(Decimal("0"), tot_dec - avail_dec)
        now = timestamp if timestamp is not None else time.time()

        prev_state = None
        if curr_key in self.balances:
            old = self.balances[curr_key]
            prev_state = CurrencyBalanceState(
                currency=old.currency,
                total=old.total,
                available=old.available,
                reserved=old.reserved,
                last_updated_at=old.last_updated_at,
                version=old.version,
                source=old.source,
            )
            new_version = old.version + 1
        else:
            new_version = 1

        new_state = CurrencyBalanceState(
            currency=curr_key,
            total=tot_dec,
            available=avail_dec,
            reserved=res_dec,
            last_updated_at=now,
            version=new_version,
            source=source,
        )
        self.balances[curr_key] = new_state
        return new_state, prev_state
