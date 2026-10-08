from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from src.core.severity import Severity
from src.exchange.managers.rest_manager import RestManager
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.accounts.account_manager import AccountManager
from src.trading.reconciliation.models.discrepancy import (
    Discrepancy,
    DiscrepancyType,
)
from src.trading.reconciliation.reconcilers.base_reconciler import BaseReconciler
from src.trading.session.session_manager import SessionManager




class BalanceReconciler(ApplicationLoggingMixin, BaseReconciler):
    DEFAULT_CRITICAL_THRESHOLD = Decimal("1.00")
    DEFAULT_WARNING_THRESHOLD = Decimal("0.0001")

    def __init__(
            self,
            account_manager: AccountManager,
            rest_manager: RestManager,
            session_manager: Optional[SessionManager] = None,
            critical_threshold: Decimal = DEFAULT_CRITICAL_THRESHOLD,
            warning_threshold: Decimal = DEFAULT_WARNING_THRESHOLD,
    ):
        self._account_manager = account_manager
        self._rest_manager = rest_manager
        self._session_manager = session_manager
        self._critical_threshold = critical_threshold
        self._warning_threshold = warning_threshold

    def reconcile(self, exchange: str, assets: List[Asset]) -> List[Discrepancy]:
        discrepancies: List[Discrepancy] = []
        ex_key = exchange.upper()

        try:
            exchange_balances: List[AccountBalance] = self._rest_manager.get_account_balance(
                exchange, force_refresh=True
            )
        except TypeError:
            exchange_balances = self._rest_manager.get_account_balance(exchange)
        except Exception as exc:
            self.app_logger.warning("Failed to fetch authoritative balances from %s: %s", exchange, exc)
            return discrepancies

        if not exchange_balances:
            return discrepancies

        exchange_map = {
            b.currency.upper(): Decimal(str(b.available_balance))
            for b in exchange_balances
        }

        local_map: dict[str, Decimal] = {}
        with self._account_manager._lock:
            if ex_key in self._account_manager.balances:
                for curr, bal in self._account_manager.balances[ex_key].items():
                    local_map[curr.upper()] = Decimal(str(bal.available_balance))

        managed_currencies = {
                                 str(asset.quote_ticker_symbol).upper()
                                 for asset in assets
                                 if asset.exchange.value.upper() == ex_key
                             } | {
                                 str(asset.base_ticker_symbol).upper()
                                 for asset in assets
                                 if asset.exchange.value.upper() == ex_key
                             }

        currencies_to_check = (set(exchange_map.keys()) & managed_currencies) | set(local_map.keys())

        for currency in currencies_to_check:
            if currency not in local_map:
                continue

            ex_val = exchange_map.get(currency, Decimal("0"))
            loc_val = local_map.get(currency, Decimal("0"))
            diff = ex_val - loc_val

            if abs(diff) > self._warning_threshold:
                severity = (
                    Severity.CRITICAL
                    if abs(diff) >= self._critical_threshold
                    else Severity.WARNING
                )
                action = "TRADING_PAUSED_AND_LOCAL_SYNCED" if severity == Severity.CRITICAL else "LOCAL_STATE_SYNCED"

                discrepancy = Discrepancy(
                    discrepancy_type=DiscrepancyType.BALANCE_MISMATCH,
                    severity=severity,
                    exchange=ex_key,
                    asset_or_currency=currency,
                    local_value=f"{currency} {loc_val}",
                    exchange_value=f"{currency} {ex_val}",
                    difference=diff,
                    action_taken=action,
                    details={
                        "local_available": str(loc_val),
                        "exchange_available": str(ex_val),
                        "threshold": str(self._critical_threshold),
                    },
                )
                discrepancies.append(discrepancy)
                self.app_logger.warning("Balance discrepancy on %s: %s", ex_key, discrepancy.format_alert())

        self._account_manager._cache_balances(
            ex_key,
            exchange_balances,
            source="REST_RECONCILIATION",
            reason="AUTHORITATIVE_SYNC",
        )

        if self._session_manager:
            for asset in assets:
                if asset.exchange.value.upper() == ex_key:
                    quote_sym = str(asset.quote_ticker_symbol).upper()
                    if quote_sym in exchange_map:
                        self._session_manager.update_available_balance(
                            asset.key, exchange_map[quote_sym]
                        )

        return discrepancies
