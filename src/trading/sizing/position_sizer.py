from __future__ import annotations

import logging
from decimal import Decimal, ROUND_DOWN
from typing import Optional

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trading_context import TradingContext
from src.configuration.trading_config import TradingConfig
from src.core.expressions.expression_parser import ExpressionParser
from src.trading.consensus.consensus_decision import ConsensusDecision
from src.trading.factories.trading_expression_factory import TradingExpressionFactory
from src.trading.protection.portfolio_policy_resolver import EffectivePortfolioConfig
from src.trading.protection.quote_portfolio_guard import PortfolioRiskMetrics

logger = logging.getLogger(__name__)


class PositionSizer:
    def __init__(
            self,
            global_formula: Optional[str] = None,
            assets: Optional[list[Asset]] = None,
    ) -> None:
        self._global_formula = global_formula
        self._global_parser = (
            ExpressionParser(global_formula.strip())
            if isinstance(global_formula, str) and global_formula.strip()
            else None
        )
        self._asset_parsers: dict[int, ExpressionParser] = {}
        if assets:
            self.rebuild_asset_parsers(assets)

    @classmethod
    def from_config(cls, config: TradingConfig) -> PositionSizer:
        return cls(global_formula=config.dynamic_quantity, assets=config.assets)

    @property
    def global_formula(self) -> Optional[str]:
        return self._global_formula

    @property
    def global_parser(self) -> Optional[ExpressionParser]:
        return self._global_parser

    @global_parser.setter
    def global_parser(self, parser: Optional[ExpressionParser]) -> None:
        self._global_parser = parser

    def rebuild_asset_parsers(self, assets: list[Asset]) -> None:
        self._asset_parsers = {}
        for asset in assets:
            dq = asset.dynamic_quantity
            if isinstance(dq, str) and dq.strip():
                self._asset_parsers[asset.key] = ExpressionParser(dq.strip())

    def get_parser(self, asset: Asset) -> Optional[ExpressionParser]:
        dq = asset.dynamic_quantity
        if isinstance(dq, str) and dq.strip():
            if asset.key in self._asset_parsers:
                return self._asset_parsers[asset.key]
            return ExpressionParser(dq.strip())
        return self._global_parser

    def update_config(self, trading_config: TradingConfig) -> None:
        if trading_config.dynamic_quantity != self._global_formula:
            self._global_formula = trading_config.dynamic_quantity
            self._global_parser = (
                ExpressionParser(trading_config.dynamic_quantity.strip())
                if isinstance(trading_config.dynamic_quantity, str) and trading_config.dynamic_quantity.strip()
                else None
            )
            logger.info("Config updated: dynamic_quantity to %r", trading_config.dynamic_quantity)

        self.rebuild_asset_parsers(trading_config.assets)

    def calculate_quantity(
            self,
            asset: Asset,
            market_data: MarketData,
            decision: ConsensusDecision,
            account_balance: Optional[AccountBalance],
            trading_context: Optional[TradingContext],
            candles: list[Candle],
            risk_metrics: Optional[PortfolioRiskMetrics] = None,
            effective_config: Optional[EffectivePortfolioConfig] = None,
    ) -> Decimal:
        minimum_order_quantity = Decimal(str(asset.min_quantity))
        parser = self.get_parser(asset)

        if parser is None or trading_context is None:
            return minimum_order_quantity

        try:
            context = TradingExpressionFactory.create_context(
                asset=asset,
                market_data=market_data,
                account_balance=account_balance,
                trading_context=trading_context,
                decision=decision,
                candles=candles,
                risk_metrics=risk_metrics,
                effective_config=effective_config,
            )

            raw_result = parser.parse(context)
            if raw_result is None:
                return minimum_order_quantity

            quantity = Decimal(str(raw_result))
            quantum = Decimal("1").scaleb(-asset.quantity_decimals)
            quantity = quantity.quantize(quantum, rounding=ROUND_DOWN)

            if quantity < minimum_order_quantity:
                logger.info(
                    "Calculated quantity %s for %s is below min_quantity %s; fallback to min_quantity",
                    quantity, asset.ticker_symbol, minimum_order_quantity,
                )
                return minimum_order_quantity

            return max(quantity, minimum_order_quantity)

        except Exception:
            logger.exception(
                "Failed to calculate dynamic quantity; fallback to min_quantity.",
                extra={"asset": asset.ticker_symbol},
            )
            return minimum_order_quantity
