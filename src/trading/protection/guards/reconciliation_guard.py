from __future__ import annotations

from typing import Optional

from api.interfaces.asset import Asset
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.configuration.guard_config import GuardConfig
from src.core.interfaces.guard import Guard


class ReconciliationGuard(Guard):
    def __init__(
            self,
            config: Optional[GuardConfig] = None,
            reconciliation_engine=None,
    ):
        super().__init__(config or GuardConfig())
        self._reconciliation_engine = reconciliation_engine

    def set_engine(self, reconciliation_engine) -> None:
        self._reconciliation_engine = reconciliation_engine

    def can_trade(
            self,
            trade_action: TradeAction,
            trading_context: TradingContext,
            market_data: MarketData,
    ) -> bool:
        if not self._reconciliation_engine:
            return True
        return not self._reconciliation_engine.has_critical_discrepancy(
            exchange=trading_context.exchange,
            symbol=trading_context.ticker_symbol,
        )

    @staticmethod
    def is_enabled(asset: Asset) -> bool:
        return True
