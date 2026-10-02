from __future__ import annotations

from decimal import Decimal
from typing import List

from api.interfaces.asset import Asset
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.accounts.account_manager import AccountManager
from src.trading.reconciliation.models.discrepancy import (
    Discrepancy,
    DiscrepancySeverity,
    DiscrepancyType,
)
from src.trading.reconciliation.reconcilers.base_reconciler import BaseReconciler
from src.trading.session.session_manager import SessionManager


class PositionReconciler(ApplicationLoggingMixin, BaseReconciler):
    DEFAULT_DUST_THRESHOLD = Decimal("0.00000001")
    DEFAULT_CRITICAL_THRESHOLD = Decimal("0.001")

    def __init__(
            self,
            session_manager: SessionManager,
            account_manager: AccountManager,
            critical_threshold: Decimal = DEFAULT_CRITICAL_THRESHOLD,
            dust_threshold: Decimal = DEFAULT_DUST_THRESHOLD,
    ):
        self._session_manager = session_manager
        self._account_manager = account_manager
        self._critical_threshold = critical_threshold
        self._dust_threshold = dust_threshold

    def reconcile(self, exchange: str, assets: List[Asset]) -> List[Discrepancy]:
        discrepancies: List[Discrepancy] = []
        ex_key = exchange.upper()

        for asset in assets:
            if asset.exchange.value.upper() != ex_key:
                continue

            trading_context = self._session_manager.get_trading_context(asset.key)
            if trading_context is None:
                continue

            local_qty = Decimal(str(trading_context.position_qty))
            base_balance = self._account_manager.get_base_balance(asset, asset.exchange.value)
            exchange_qty = Decimal(str(base_balance.available_balance)) if base_balance else Decimal("0")

            diff = exchange_qty - local_qty
            if abs(diff) > self._dust_threshold:
                severity = (
                    DiscrepancySeverity.CRITICAL
                    if abs(diff) >= self._critical_threshold
                    else DiscrepancySeverity.WARNING
                )
                action = (
                    "TRADING_PAUSED_AND_LOCAL_SYNCED"
                    if severity == DiscrepancySeverity.CRITICAL
                    else "LOCAL_STATE_SYNCED"
                )

                discrepancy = Discrepancy(
                    discrepancy_type=DiscrepancyType.POSITION_MISMATCH,
                    severity=severity,
                    exchange=ex_key,
                    asset_or_currency=asset.ticker_symbol,
                    local_value=f"QTY {local_qty}",
                    exchange_value=f"QTY {exchange_qty}",
                    difference=diff,
                    action_taken=action,
                    details={
                        "local_position_qty": str(local_qty),
                        "exchange_base_qty": str(exchange_qty),
                    },
                )
                discrepancies.append(discrepancy)
                self.app_logger.warning("Position discrepancy for %s on %s: %s", asset.ticker_symbol, ex_key, discrepancy.format_alert())

                # Authoritative sync of position
                trading_context.position_qty = exchange_qty

        return discrepancies
