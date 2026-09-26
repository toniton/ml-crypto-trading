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
from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.core.interfaces.trading_strategy import TradingStrategy
from src.configuration.trading_config import TradingConfig
from src.core.expressions.expression_parser import ExpressionParser
from src.trading.consensus.consensus_decision import ConsensusDecision
from src.trading.events import (
    BalanceChangedEvent,
    DecisionRejectedEvent,
    DecisionRejectedReason,
    MarketDataEvent,
    MarketStateChangedEvent,
    OrderSubmittedEvent,
    SignalGeneratedEvent,
    StrategyEvaluatedEvent,
)
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
            strategies_registry: Optional[StrategyRegistry] = None,
            event_bus: Optional[EventBus] = None
    ):
        self.assets = assets
        self.event_bus = event_bus
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
            if config_asset.enabled != current_asset.enabled:
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
            self._publish_event(DecisionRejectedEvent(
                symbol=asset.ticker_symbol,
                action=action.value,
                reason=DecisionRejectedReason.GUARD_HALT.value,
                details={"reason": "Protection manager prevented trade"},
            ))
            return None

        decision = self.consensus_manager.evaluate(
            action, asset.ticker_symbol, trading_context, market_data, candles
        )
        self._publish_event(StrategyEvaluatedEvent(
            symbol=asset.ticker_symbol,
            evaluated_at=float(market_data.timestamp),
        ))
        if decision is not None and decision.quorum:
            self._publish_event(SignalGeneratedEvent(
                symbol=asset.ticker_symbol,
                action=action.value,
                generated_at=float(market_data.timestamp),
            ))
        elif decision is not None and not decision.quorum:
            self._publish_event(DecisionRejectedEvent(
                symbol=asset.ticker_symbol,
                action=action.value,
                reason=DecisionRejectedReason.NO_QUORUM.value,
                details={
                    "buy_votes": decision.true_count if action == TradeAction.BUY else 0,
                    "sell_votes": decision.true_count if action == TradeAction.SELL else 0,
                    "total": decision.total,
                },
            ))
        self.app_logger.debug(f"Consensus={decision.quorum} for asset={asset}")
        return decision

    def _prepare_trade_context(self, asset: Asset) -> tuple[AccountBalance, MarketData, list[Candle], Fees]:
        quote_balance = self.account_manager.get_quote_balance(asset, asset.exchange.value)
        if self.session_manager:
            self.session_manager.update_available_balance(asset.key, quote_balance.available_balance)
        if quote_balance.available_balance <= 0:
            self.app_logger.debug(f"Balance too low for {asset}: {quote_balance}")
            raise ValueError(f"Insufficient balance for {asset.quote_ticker_symbol}")

        market_data = self.market_data_manager.get_market_data(asset)
        self.app_logger.debug(f"Fetched market data for {asset}: {market_data}")
        fees = self.fees_manager.get_instrument_fees(asset.exchange.value, asset.ticker_symbol)
        candles = self.market_data_manager.get_candles(asset)

        self._publish_event(MarketStateChangedEvent(
            symbol=asset.ticker_symbol,
            price=market_data.close_price,
            market_timestamp=market_data.timestamp,
        ))
        self._publish_event(MarketDataEvent(
            ticker_symbol=asset.ticker_symbol,
            market_data=market_data,
        ))
        self._publish_event(BalanceChangedEvent(
            symbol=asset.ticker_symbol,
            currency=asset.quote_ticker_symbol,
            balance=quote_balance.available_balance,
        ))

        return quote_balance, market_data, candles, fees

    def create_buy_order(self, assets: list[Asset]):
        for asset in assets:
            if not asset.enabled:
                self.app_logger.debug("Skipping BUY for disabled asset %s", asset.ticker_symbol)
                continue
            try:
                self._process_buy_asset(asset)
            except Exception as exc:  # pylint: disable=broad-except
                self.app_logger.error(f"Error processing asset {asset}: {exc}", exc_info=True)

    def _process_buy_asset(self, asset: Asset) -> None:
        if self.session_manager and self.session_manager.get_trading_context(asset.key) is None:
            if self.account_manager and not self.account_manager.init_asset_balance(
                    asset, self.session_manager
            ):
                self.app_logger.debug("Skipping BUY for uninitialized context %s", asset.ticker_symbol)
                return

        account_balance, market_data, candles, fees = self._prepare_trade_context(asset)
        trading_context = (
            self.session_manager.get_trading_context(asset.key)
            if self.session_manager else None
        )
        if trading_context is None and self.session_manager is not None:
            self.app_logger.debug("Skipping BUY for uninitialized context %s", asset.ticker_symbol)
            return

        decision = self._evaluate_decision(asset, TradeAction.BUY, trading_context, market_data, candles)
        if decision is None or not decision.quorum:
            self.app_logger.debug("No consensus to buy %s", asset.ticker_symbol)
            return

        self.app_logger.info("Consensus reached to buy %s", asset.ticker_symbol)
        price = self._calculate_price(asset, market_data, fees)

        if self.order_manager.has_outstanding_intent(asset.ticker_symbol, TradeAction.BUY):
            self.app_logger.debug(
                "Skipping BUY for %s: outstanding order intent already in progress",
                asset.ticker_symbol
            )
            self._publish_event(DecisionRejectedEvent(
                symbol=asset.ticker_symbol,
                action=TradeAction.BUY.value,
                reason=DecisionRejectedReason.OUTSTANDING_INTENT.value,
            ))
            return

        if not self._validate_execution_edge(asset, TradeAction.BUY, market_data, fees):
            return

        quantity_val = self._calculate_quantity(asset, TradeAction.BUY, market_data, decision)
        if quantity_val is None:
            return

        order_cost = price * quantity_val
        if order_cost > account_balance.available_balance:
            self.app_logger.warning(
                "Rejected BUY for %s: required cost %s exceeds available balance %s",
                asset.ticker_symbol, order_cost, account_balance.available_balance
            )
            self._publish_event(DecisionRejectedEvent(
                symbol=asset.ticker_symbol,
                action=TradeAction.BUY.value,
                reason=DecisionRejectedReason.INSUFFICIENT_BALANCE.value,
                details={
                    "order_cost": str(order_cost),
                    "available_balance": str(account_balance.available_balance),
                },
            ))
            return

        quantity = format(quantity_val, "f")
        self._submit_buy_order(asset, price, quantity, market_data, decision)

    def _submit_buy_order(
            self,
            asset: Asset,
            price: Decimal,
            quantity: str,
            market_data: MarketData,
            decision: ConsensusDecision,
    ) -> None:
        commit_hash = self.session_manager.get_current_commit_hash()
        winning_strategy = self._resolve_winning_strategy(decision)
        strategy_votes = self._format_strategy_votes(decision)
        buy_order = self.order_manager.open_order(
            ticker_symbol=asset.ticker_symbol,
            quantity=quantity,
            price=price,
            provider_name=asset.exchange.value,
            trade_action=TradeAction.BUY,
            timestamp=market_data.timestamp,
            commit_hash=commit_hash,
            winning_strategy=winning_strategy,
            strategy_votes=strategy_votes,
        )
        self.activity_queue.put_nowait(buy_order.model_dump_json())

        self._publish_event(OrderSubmittedEvent(
            symbol=asset.ticker_symbol,
            order=buy_order,
        ))

        self.trading_logger.info("Order opened: %s BUY %s @ %s", asset.ticker_symbol, quantity, price)
        self.log_audit_event(
            event_type='order_opened',
            asset=asset.ticker_symbol,
            action=TradeAction.BUY.value,
            market_data=market_data,
            context=f'order_id={buy_order.uuid},price={price},quantity={quantity},commit_hash={commit_hash}'
        )

    def create_sell_order(self, assets: list[Asset]):
        for asset in assets:
            if not asset.enabled:
                self.app_logger.debug("Skipping SELL for disabled asset %s", asset.ticker_symbol)
                continue
            try:
                self._process_sell_asset(asset)
            except Exception as exc:  # pylint: disable=broad-except
                self.app_logger.error(f"Error finalizing asset {asset}: {exc}", exc_info=True)
        self.app_logger.debug("Check unclosed orders completed")

    def _process_sell_asset(self, asset: Asset) -> None:
        trading_context = self.session_manager.get_trading_context(asset.key) if self.session_manager else None
        if trading_context is None and self.session_manager and self.account_manager:
            if not self.account_manager.init_asset_balance(asset, self.session_manager):
                return
            trading_context = self.session_manager.get_trading_context(asset.key)
        if not trading_context or not trading_context.open_positions:
            self.app_logger.debug("No open positions for %s", asset)
            return

        if self.order_manager.has_outstanding_intent(asset.ticker_symbol, TradeAction.SELL):
            self.app_logger.debug(
                "Skipping SELL for %s: outstanding order intent already in progress",
                asset.ticker_symbol
            )
            self._publish_event(DecisionRejectedEvent(
                symbol=asset.ticker_symbol,
                action=TradeAction.SELL.value,
                reason=DecisionRejectedReason.OUTSTANDING_INTENT.value,
            ))
            return

        _, market_data, candles, fees = self._prepare_trade_context(asset)
        base_balance = self.account_manager.get_base_balance(asset, asset.exchange.value)

        price = self._calculate_price(asset, market_data, fees)
        decision = self._evaluate_decision(asset, TradeAction.SELL, trading_context, market_data, candles)
        if decision is None or not decision.quorum:
            return

        if not self._validate_execution_edge(asset, TradeAction.SELL, market_data, fees):
            return

        quantity_val = self._calculate_quantity(asset, TradeAction.SELL, market_data, decision)
        if quantity_val is None:
            return
        quantity = format(quantity_val, "f")
        if base_balance.available_balance >= quantity_val:
            self._submit_sell_order(asset, price, quantity, market_data, decision)

    def _submit_sell_order(
            self,
            asset: Asset,
            price: Decimal,
            quantity: str,
            market_data: MarketData,
            decision: ConsensusDecision,
    ) -> None:
        commit_hash = self.session_manager.get_current_commit_hash()
        winning_strategy = self._resolve_winning_strategy(decision)
        strategy_votes = self._format_strategy_votes(decision)
        sell_order = self.order_manager.open_order(
            price=price, trade_action=TradeAction.SELL,
            quantity=quantity, provider_name=asset.exchange.value,
            ticker_symbol=asset.ticker_symbol, timestamp=market_data.timestamp,
            commit_hash=commit_hash,
            winning_strategy=winning_strategy,
            strategy_votes=strategy_votes,
        )
        self.activity_queue.put_nowait(sell_order.model_dump_json())

        self._publish_event(OrderSubmittedEvent(
            symbol=asset.ticker_symbol,
            order=sell_order,
        ))

        self.trading_logger.info("Order closed: %s SELL %s @ %s", asset.ticker_symbol, quantity, price)
        self.log_audit_event(
            event_type='order_closed',
            asset=asset.ticker_symbol,
            action=TradeAction.SELL.value,
            market_data=market_data,
            context=f'order_id={sell_order.uuid},price={price},quantity={quantity},commit_hash={commit_hash}'
        )

    def _publish_event(self, event: Event) -> None:
        if self.event_bus is None:
            return
        try:
            self.event_bus.publish(event)
        except Exception:  # pylint: disable=broad-except
            self.app_logger.exception(f"Failed to publish {event.type}")

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

    def _validate_execution_edge(
            self,
            asset: Asset,
            action: TradeAction,
            market_data: MarketData,
            fees: Fees,
    ) -> bool:
        if fees is None:
            return True

        maker_fee_pct = Decimal(str(fees.maker_fee_pct)) if fees.maker_fee_pct is not None else Decimal(0)
        taker_fee_pct = Decimal(str(fees.taker_fee_pct)) if fees.taker_fee_pct is not None else Decimal(0)
        round_trip_friction_pct = maker_fee_pct + taker_fee_pct

        spread_pct = Decimal(0)
        if (
                market_data.bid_price is not None
                and market_data.ask_price is not None
                and market_data.bid_price > Decimal(0)
        ):
            spread = market_data.ask_price - market_data.bid_price
            spread_pct = (spread / market_data.bid_price) * Decimal(100)

        total_cost_pct = round_trip_friction_pct + spread_pct

        if total_cost_pct > Decimal("10.0"):
            self.app_logger.warning(
                "Rejected %s for %s: total execution friction %s%% exceeds maximum tolerable threshold",
                action.value, asset.ticker_symbol, total_cost_pct,
            )
            self._publish_event(DecisionRejectedEvent(
                symbol=asset.ticker_symbol,
                action=action.value,
                reason=DecisionRejectedReason.NEGATIVE_EDGE.value,
                details={
                    "total_cost_pct": str(total_cost_pct),
                    "fees_pct": str(round_trip_friction_pct),
                },
            ))
            return False

        return True

    def _calculate_price(self, asset: Asset, market_data: MarketData, fees: Fees) -> Decimal:
        price = Decimal(market_data.close_price)
        fee_multiplier = Decimal("1") + (Decimal(fees.maker_fee_pct) / Decimal("100"))
        quantum = Decimal("1").scaleb(-asset.quote_decimals)
        return (price * fee_multiplier).quantize(quantum, rounding=ROUND_UP)

    @staticmethod
    def _resolve_winning_strategy(decision: Optional[ConsensusDecision]) -> Optional[str]:
        if not decision or not decision.votes:
            return None
        positive_votes = [
            (name, decision.weights.get(name, 1.0))
            for name, vote in decision.votes.items()
            if vote
        ]
        if not positive_votes:
            return None
        positive_votes.sort(key=lambda x: x[1], reverse=True)
        return positive_votes[0][0]

    @staticmethod
    def _format_strategy_votes(decision: Optional[ConsensusDecision]) -> Optional[dict[str, str]]:
        if not decision or not decision.votes:
            return None
        return {name: "TRUE" if vote else "FALSE" for name, vote in decision.votes.items()}

    def _calculate_quantity(
            self, asset: Asset, _action: TradeAction,
            market_data: MarketData, decision: ConsensusDecision
    ) -> Decimal:
        minimum_order_quantity = Decimal(str(asset.min_quantity))

        if self._dynamic_quantity_parser is None:
            return minimum_order_quantity

        try:
            quantity = self._evaluate_dynamic_quantity(asset, market_data, decision)

            if quantity is None:
                return minimum_order_quantity

            quantum = Decimal("1").scaleb(-asset.quantity_decimals)
            quantity = quantity.quantize(quantum, rounding=ROUND_DOWN)

            if quantity < minimum_order_quantity:
                self.app_logger.info(
                    "Calculated quantity %s for %s is below min_quantity %s; fallback to min_quantity",
                    quantity, asset.ticker_symbol, minimum_order_quantity,
                )
                return minimum_order_quantity

            return max(quantity, minimum_order_quantity)

        except Exception:
            self.app_logger.exception(
                "Failed to calculate dynamic quantity; fallback to min_quantity.",
                extra={"asset": asset.ticker_symbol},
            )
            return minimum_order_quantity

    def _evaluate_dynamic_quantity(
            self,
            asset: Asset,
            market_data: MarketData,
            decision: ConsensusDecision,
    ) -> Decimal | None:
        trading_context = self.session_manager.get_trading_context(asset.key)
        if trading_context is None:
            return None
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
