from __future__ import annotations

import uuid
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from queue import Queue
from typing import Optional

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_session import TradingSession
from api.interfaces.trading_context import TradingContext
from src.core.interfaces.trading_strategy import TradingStrategy
from src.configuration.trading_config import TradingConfig
from src.core.expressions.expression_parser import ExpressionParser
from src.trading.consensus.consensus_decision import ConsensusDecision
from src.trading.factories.trading_expression_factory import TradingExpressionFactory
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.logging.audit_logging_mixin import AuditLoggingMixin
from src.logging.trading_logging_mixin import TradingLoggingMixin
from src.trading.managers.manager_container import ManagerContainer
from src.trading.strategies.strategy_registry import StrategyRegistry
from src.trading.strategies.strategy_resolver import StrategyResolver


class TradingExecutor(ApplicationLoggingMixin, TradingLoggingMixin, AuditLoggingMixin):

    def __init__(
            self,
            assets: list[Asset],
            manager_container: ManagerContainer,
            activity_queue: Queue,
            dynamic_quantity: Optional[str] = None,
            strategies_registry: Optional[StrategyRegistry] = None
    ):
        self.assets = assets
        self._dynamic_quantity = dynamic_quantity
        self._dynamic_quantity_parser = ExpressionParser(dynamic_quantity) if dynamic_quantity else None
        self.account_manager = manager_container.account_manager
        self.fees_manager = manager_container.fees_manager
        self.order_manager = manager_container.order_manager
        self.market_data_manager = manager_container.market_data_manager
        self.consensus_manager = manager_container.consensus_manager
        self.consensus_manager.set_factors(self.assets)
        self.session_manager = manager_container.session_manager
        self.protection_manager = manager_container.protection_manager
        self.websocket_manager = manager_container.websocket_manager
        self.activity_queue = activity_queue
        self._strategies_registry = strategies_registry or StrategyRegistry()
        self._strategies: list[TradingStrategy] = []
        self._register_asset_strategies(self.assets)

    def _register_asset_strategies(self, assets: list[Asset]) -> None:
        for asset in assets:
            for strategy in StrategyResolver.resolve_asset(asset, self._strategies_registry):
                self.consensus_manager.register_strategy(strategy)
                self._strategies.append(strategy)

    def _unregister_asset_strategies(self) -> None:
        for strategy in self._strategies:
            self.consensus_manager.unregister_strategy(strategy)
        self._strategies = []

    def update_config(self, trading_config: TradingConfig) -> None:
        self.consensus_manager.set_factors(trading_config.assets)

        if trading_config.dynamic_quantity != self._dynamic_quantity:
            self._dynamic_quantity = trading_config.dynamic_quantity
            self._dynamic_quantity_parser = (
                ExpressionParser(trading_config.dynamic_quantity) if trading_config.dynamic_quantity else None
            )
            self.app_logger.info("Config updated: dynamic_quantity to %r", trading_config.dynamic_quantity)

        if self._assets_changed(trading_config.assets, self.assets):
            self._unregister_asset_strategies()
            self.assets = trading_config.assets
            self._register_asset_strategies(self.assets)
            self.app_logger.info(
                "Config updated: strategies re-registered for %s",
                [asset.ticker_symbol for asset in self.assets]
            )

    @staticmethod
    def _assets_changed(config_assets: list[Asset], current_assets: list[Asset]) -> bool:
        if len(config_assets) != len(current_assets):
            return True
        for config_asset, current_asset in zip(config_assets, current_assets):
            if config_asset.ticker_symbol != current_asset.ticker_symbol:
                return True
            if (config_asset.strategies or []) != (current_asset.strategies or []):
                return True
        return False

    def init_application(self):
        self.session_manager.create_session(session_id=str(uuid.uuid4())).start_session()
        self.account_manager.init_account_balances(self.session_manager)
        self.fees_manager.init_fees()
        self.websocket_manager.connect()
        self.account_manager.init_websocket()
        self.order_manager.initialize(self.assets)
        self.market_data_manager.initialize(self.assets)

    def _evaluate_decision(
            self, asset: Asset, action: TradeAction,
            trading_context: TradingContext,
            market_data: MarketData, candles: list[Candle]
    ) -> Optional[ConsensusDecision]:
        if not self.protection_manager.can_trade(asset.key, action, trading_context, market_data):
            return None

        decision = self.consensus_manager.evaluate(
            action, asset.ticker_symbol, trading_context, market_data, candles
        )
        self.app_logger.debug(f"Consensus={decision.quorum} for asset={asset}")
        return decision

    def _prepare_trade_context(self, asset: Asset) -> tuple[AccountBalance, MarketData, list[Candle], Fees]:
        quote_balance = self.account_manager.get_quote_balance(asset, asset.exchange.value)
        self.session_manager.update_available_balance(asset.key, quote_balance.available_balance)
        if quote_balance.available_balance <= 0:
            self.app_logger.debug(f"Balance too low for {asset}: {quote_balance}")
            raise ValueError(f"Insufficient balance for {asset.quote_ticker_symbol}")

        market_data = self.market_data_manager.get_market_data(asset)
        self.app_logger.debug(f"Fetched market data for {asset}: {market_data}")
        fees = self.fees_manager.get_instrument_fees(asset.exchange.value, asset.ticker_symbol)
        candles = self.market_data_manager.get_candles(asset)

        return quote_balance, market_data, candles, fees

    def create_buy_order(self, assets: list[Asset]):
        for asset in assets:
            try:
                account_balance, market_data, candles, fees = self._prepare_trade_context(asset)
                trading_context = self.session_manager.get_trading_context(asset.key)
                decision = self._evaluate_decision(
                    asset, TradeAction.BUY, trading_context, market_data, candles
                )
                if decision is None or not decision.quorum:
                    self.app_logger.debug(f"No consensus to buy {asset.ticker_symbol}")
                    continue

                self.app_logger.info(f"Consensus reached to buy {asset.ticker_symbol}")

                price = self._calculate_price(asset, market_data, fees)

                self.app_logger.debug([
                    f"Calculated price for {asset}: Price={price}",
                    f"Fees={fees}",
                    f"Available balance={account_balance.available_balance}"
                ])
                quantity = format(
                    self._calculate_quantity(asset, TradeAction.BUY, market_data, decision), "f"
                )
                buy_order = self.order_manager.open_order(
                    ticker_symbol=asset.ticker_symbol,
                    quantity=quantity,
                    price=price,
                    provider_name=asset.exchange.value,
                    trade_action=TradeAction.BUY,
                    timestamp=market_data.timestamp
                )
                self.activity_queue.put_nowait(buy_order.model_dump_json())
                self.session_manager.record_position(
                    asset.key, market_data, TradeAction.BUY,
                    quantity=Decimal(quantity), price=price
                )

                self.trading_logger.info(f"Order opened: {asset.ticker_symbol} BUY {quantity} @ {price}")

                self.log_audit_event(
                    event_type='order_opened',
                    asset=asset.ticker_symbol,
                    action=TradeAction.BUY.value,
                    market_data=market_data,
                    context=f'order_id={buy_order.uuid},price={price},quantity={quantity}'
                )
            except Exception as exc:
                self.app_logger.error(f"Error processing asset {asset}: {exc}", exc_info=True)

    def create_sell_order(self, assets: list[Asset]):
        for asset in assets:
            try:
                trading_context = self.session_manager.get_trading_context(asset.key)
                if not trading_context.open_positions:
                    self.app_logger.debug(f"No open positions for {asset}")
                    continue
                _, market_data, candles, fees = self._prepare_trade_context(asset)
                base_balance = self.account_manager.get_base_balance(asset, asset.exchange.value)

                price = self._calculate_price(asset, market_data, fees)

                self.app_logger.debug(f"Current price for {asset}: {price}, Fees={fees}")

                decision = self._evaluate_decision(
                    asset, TradeAction.SELL, trading_context, market_data, candles
                )
                if decision is None or not decision.quorum:
                    continue

                open_positions: list[MarketData] = sorted(
                    trading_context.open_positions,
                    key=lambda o, _current_price=market_data.close_price:
                    (float(_current_price) - float(o.close_price)) / float(o.close_price)
                )

                quantity_val = self._calculate_quantity(asset, TradeAction.SELL, market_data, decision)
                quantity = format(quantity_val, "f")
                best_position: MarketData | None = next(iter(open_positions), None)
                if best_position and base_balance.available_balance >= quantity_val:
                    sell_order = self.order_manager.open_order(
                        price=price, trade_action=TradeAction.SELL,
                        quantity=quantity, provider_name=asset.exchange.value,
                        ticker_symbol=asset.ticker_symbol, timestamp=market_data.timestamp
                    )
                    self.activity_queue.put_nowait(sell_order.model_dump_json())
                    self.session_manager.record_position(
                        asset.key, market_data, TradeAction.SELL,
                        quantity=Decimal(quantity), price=price
                    )

                    self.trading_logger.info(
                        f"Order closed: {asset.ticker_symbol} SELL {quantity} @ {price}")

                    self.log_audit_event(
                        event_type='order_closed',
                        asset=asset.ticker_symbol,
                        action=TradeAction.SELL.value,
                        market_data=market_data,
                        context=f'order_id={sell_order.uuid},price={price},quantity={quantity}'
                    )

            except Exception as exc:
                self.app_logger.error(f"Error finalizing asset {asset}: {exc}", exc_info=True)
        self.app_logger.debug("Check unclosed orders completed")

    def stop(self):
        self.market_data_manager.shutdown()
        self.order_manager.shutdown()
        self.account_manager.shutdown()
        self.account_manager.close_account_balances(self.session_manager)
        session = self.session_manager.end_session()
        self._print_session_summary(session)

    def _print_session_summary(self, session: TradingSession) -> None:
        session_summary = self.session_manager.get_session_summary(session)
        self.app_logger.info("Trading Context Summary")
        self.app_logger.info("==============================")
        self.app_logger.info(session_summary)
        self.app_logger.info("------------------------------")

    def _calculate_price(self, asset: Asset, market_data: MarketData, fees: Fees) -> Decimal:
        price = Decimal(market_data.close_price)
        fee_multiplier = Decimal("1") + (Decimal(fees.maker_fee_pct) / Decimal("100"))
        quantum = Decimal("1").scaleb(-asset.quote_decimals)
        return (price * fee_multiplier).quantize(quantum, rounding=ROUND_UP)

    def _calculate_quantity(
            self, asset: Asset, action: TradeAction,  # pylint: disable=unused-argument
            market_data: MarketData, decision: ConsensusDecision
    ) -> Decimal:
        fallback_quantity = Decimal(str(asset.min_quantity))

        if self._dynamic_quantity_parser is None:
            return fallback_quantity

        try:
            quantity = self._evaluate_dynamic_quantity(asset, market_data, decision)

            if quantity is None:
                return fallback_quantity

            quantum = Decimal("1").scaleb(-asset.quantity_decimals)
            quantity = quantity.quantize(quantum, rounding=ROUND_DOWN)

            return max(quantity, fallback_quantity)

        except Exception:
            self.app_logger.exception(
                "Failed to calculate dynamic quantity.",
                extra={"asset": asset.ticker_symbol},
            )
            return fallback_quantity

    def _evaluate_dynamic_quantity(
            self,
            asset: Asset,
            market_data: MarketData,
            decision: ConsensusDecision,
    ) -> Decimal | None:
        trading_context = self.session_manager.get_trading_context(asset.key)
        account_balance = self.account_manager.get_quote_balance(asset, asset.exchange.value)
        candles = self.market_data_manager.get_candles(asset)

        context = TradingExpressionFactory.create_context(
            asset=asset,
            market_data=market_data,
            account_balance=account_balance,
            trading_context=trading_context,
            decision=decision,
            candles=candles
        )

        result = self._dynamic_quantity_parser.parse(context)

        return None if result is None else Decimal(str(result))
