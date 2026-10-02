from __future__ import annotations

from decimal import Decimal
from typing import List

from api.interfaces.asset import Asset
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.fees.fees_manager import FeesManager
from src.trading.reconciliation.models.discrepancy import (
    Discrepancy,
    DiscrepancySeverity,
    DiscrepancyType,
)
from src.trading.reconciliation.reconcilers.base_reconciler import BaseReconciler




class FeeReconciler(ApplicationLoggingMixin, BaseReconciler):
    def __init__(self, fees_manager: FeesManager):
        self._fees_manager = fees_manager

    def reconcile(self, exchange: str, assets: List[Asset]) -> List[Discrepancy]:
        discrepancies: List[Discrepancy] = []
        ex_key = exchange.upper()

        for asset in assets:
            if asset.exchange.value.upper() != ex_key:
                continue

            try:
                cached_fee = self._fees_manager.get_instrument_fees(asset.exchange.value, asset.ticker_symbol)
                # Ensure maker / taker fees are non-negative and consistent
                if cached_fee and (cached_fee.maker_fee_pct < Decimal("0") or cached_fee.taker_fee_pct < Decimal("0")):
                    discrepancies.append(Discrepancy(
                        discrepancy_type=DiscrepancyType.FEE_MISMATCH,
                        severity=DiscrepancySeverity.WARNING,
                        exchange=ex_key,
                        asset_or_currency=asset.ticker_symbol,
                        local_value=f"maker: {cached_fee.maker_fee_pct}, taker: {cached_fee.taker_fee_pct}",
                        exchange_value="INVALID_NEGATIVE_FEE",
                        action_taken="LOCAL_FEES_RESET",
                        details={"ticker_symbol": asset.ticker_symbol},
                    ))
            except Exception as exc:
                self.app_logger.debug("Fee reconciliation skipped for %s on %s: %s", asset.ticker_symbol, ex_key, exc)


        return discrepancies
