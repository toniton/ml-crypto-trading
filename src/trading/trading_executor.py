from __future__ import annotations

import uuid
from decimal import Decimal, ROUND_UP
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
from src.configuration.portfolio_config import PortfolioConfig
from src.configuration.trading_config import TradingConfig
from src.core.expressions.expression_parser import ExpressionParser
from src.core.interfaces.trading_strategy import TradingStrategy

from src.trading.consensus.consensus_decision import ConsensusDecision
from src.trading.decision.trading_decision import (
    ConsensusSnapshot,
    DecisionStatus,
    HealthEvaluation,
    MarketSnapshot,
    PortfolioSnapshot,
    RegimeSnapshot,
    RiskEvaluation,
    SizingSnapshot,
    TradingDecision,
)
from src.trading.events import (
    DecisionRejectedEvent,
    DecisionRejectedReason,
    MarketDataEvent,
    MarketStateChangedEvent,
    OrderSubmittedEvent,
    SignalGeneratedEvent,
    StrategyEvaluatedEvent,
    TradingDecisionCreatedEvent,
)
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.logging.audit_logging_mixin import AuditLoggingMixin
from src.logging.trading_logging_mixin import TradingLoggingMixin
from src.trading.health.enums import TradingPermission
from src.trading.health.health_monitor import HealthMonitor
from src.trading.health.models import HealthScope
from src.trading.managers.manager_container import ManagerContainer
from src.trading.protection.portfolio_policy_resolver import PortfolioPolicyResolver
from src.trading.regimes.market_regime import MarketRegime, RegimeMetrics
from src.trading.regimes.market_regime_detector import MarketRegimeDetector
from src.trading.sizing.position_sizer import PositionSizer
from src.trading.strategies.strategy_registry import StrategyRegistry
from src.trading.strategies.strategy_resolver import StrategyResolver



class TradingExecutor(ApplicationLoggingMixin, TradingLoggingMixin, AuditLoggingMixin):
    health_monitor: Optional[HealthMonitor] = None

    def __init__(
            self,
            assets: list[Asset],
            manager_container: ManagerContainer,
            activity_queue: Queue,
            position_sizer: PositionSizer,
            strategies_registry: StrategyRegistry,
            event_bus: Optional[EventBus],
    ):
        self.assets = assets
        self.event_bus = event_bus
        self.position_sizer = position_sizer
        self.manager_container = manager_container
        self.account_manager = manager_container.account_manager
        self.fees_manager = manager_container.fees_manager
        self.order_manager = manager_container.order_manager
        self.market_data_manager = manager_container.market_data_manager
        self.consensus_manager = manager_container.consensus_manager
        self.consensus_manager.set_factors(self.assets)
        self.session_manager = manager_container.session_manager
        self.protection_manager = manager_container.protection_manager
        self.portfolio_risk_manager = manager_container.portfolio_risk_manager
        self.websocket_manager = manager_container.websocket_manager
        self.health_monitor = manager_container.health_monitor
        self.decision_manager = manager_container.decision_manager
        self._regime_detector = MarketRegimeDetector()
        self.activity_queue = activity_queue
        self._strategies_registry = strategies_registry
        self._strategies: list[TradingStrategy] = []
        self._register_asset_strategies(self.assets)

    @property
    def _dynamic_quantity(self) -> Optional[str]:
        return self.position_sizer.global_formula

    @property
    def _dynamic_quantity_parser(self) -> Optional[ExpressionParser]:
        return self.position_sizer.global_parser

    @_dynamic_quantity_parser.setter
    def _dynamic_quantity_parser(self, parser: Optional[ExpressionParser]) -> None:
        self.position_sizer.global_parser = parser

    def _get_dynamic_quantity_parser(self, asset: Asset) -> Optional[ExpressionParser]:
        return self.position_sizer.get_parser(asset)

    @property
    def strategies(self) -> list[TradingStrategy]:
        return list(self._strategies)

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

        if self.portfolio_risk_manager and trading_config.portfolio:
            self.portfolio_risk_manager.update_config(trading_config.portfolio)

        self.position_sizer.update_config(trading_config)

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
            if config_asset.dynamic_quantity != current_asset.dynamic_quantity:
                return True
        return False

    def init_application(self):
        self.session_manager.create_session(session_id=str(uuid.uuid4())).start_session()
        self.account_manager.init_account_balances()
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

        market_data = self.market_data_manager.get_market_data(asset)
        self.app_logger.debug(f"Fetched market data for {asset}: {market_data}")
        fees = self.fees_manager.get_instrument_fees(asset.exchange.value, asset.ticker_symbol)
        candles = self.market_data_manager.get_candles(asset)

        if self.portfolio_risk_manager:
            self.portfolio_risk_manager.update_cash_balance(
                asset.exchange.value, asset.quote_ticker_symbol, quote_balance.available_balance
            )
            self.portfolio_risk_manager.update_market_data(asset, market_data)

        self._publish_event(MarketStateChangedEvent(
            symbol=asset.ticker_symbol,
            price=market_data.close_price,
            market_timestamp=market_data.timestamp,
        ))
        self._publish_event(MarketDataEvent(
            ticker_symbol=asset.ticker_symbol,
            market_data=market_data,
        ))

        return quote_balance, market_data, candles, fees

    def _build_market_snapshot(self, market_data: MarketData, candles: list[Candle]) -> MarketSnapshot:
        spread_pct = None
        if market_data.bid_price is not None and market_data.ask_price is not None and market_data.ask_price > 0:
            spread_pct = (market_data.ask_price - market_data.bid_price) / market_data.ask_price
        return MarketSnapshot(
            close_price=market_data.close_price,
            bid_price=market_data.bid_price,
            ask_price=market_data.ask_price,
            spread_pct=spread_pct,
            candles_count=len(candles) if candles else 0,
        )

    def _build_regime_snapshot(self, regime_metrics: RegimeMetrics) -> RegimeSnapshot:
        return RegimeSnapshot(
            regime=regime_metrics.regime.value,
            volatility=regime_metrics.volatility,
            trend_strength=regime_metrics.trend_strength,
            spread=regime_metrics.spread,
            exposure_multiplier=float(MarketRegime.get_exposure_multiplier(regime_metrics.regime)),
        )

    def _build_consensus_snapshot(self, action: TradeAction, decision: Optional[ConsensusDecision]) -> ConsensusSnapshot:
        if decision is None:
            return ConsensusSnapshot(
                action=action,
                votes={},
                weights={},
                factor=1.0,
                quorum=False,
                quorum_margin=0.0,
                vote_ratio=0.0,
                winning_strategy=None,
            )
        return ConsensusSnapshot(
            action=decision.trade_action,
            votes=dict(decision.votes),
            weights=dict(decision.weights),
            factor=decision.factor,
            quorum=decision.quorum,
            quorum_margin=decision.quorum_margin,
            vote_ratio=decision.vote_ratio,
            winning_strategy=self._resolve_winning_strategy(decision),
        )

    def _build_portfolio_snapshot(self, asset: Asset, trading_context: Optional[TradingContext]) -> PortfolioSnapshot:
        if self.portfolio_risk_manager:
            risk_metrics = self.portfolio_risk_manager.get_risk_metrics(asset)
            return PortfolioSnapshot(
                available_cash=risk_metrics.available_cash,
                total_equity=risk_metrics.total_equity,
                current_exposure_pct=float(risk_metrics.total_exposure_pct),
                asset_exposure_pct=float(risk_metrics.asset_concentration_pct),
                drawdown_pct=float(risk_metrics.drawdown_pct),
            )
        return PortfolioSnapshot(
            available_cash=trading_context.available_balance if trading_context else Decimal("0"),
            total_equity=trading_context.closing_balance if trading_context else Decimal("0"),
            current_exposure_pct=0.0,
            asset_exposure_pct=0.0,
            drawdown_pct=0.0,
        )

    def _record_decision(self, decision: TradingDecision) -> None:
        try:
            self.decision_manager.record_decision(decision)
        except Exception as exc:  # pylint: disable=broad-except
            self.app_logger.warning("Failed to persist TradingDecision %s: %s", decision.decision_id, exc)
        self._publish_event(TradingDecisionCreatedEvent(
            decision=decision,
            symbol=decision.ticker_symbol,
            action=decision.trade_action.value,
            status=decision.status.value,
        ))

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
            if self.account_manager and not self.account_manager.init_asset_balance(asset):
                self.app_logger.debug("Skipping BUY for uninitialized context %s", asset.ticker_symbol)
                return

        account_balance, market_data, candles, fees = self._prepare_trade_context(asset)
        if account_balance.available_balance <= 0:
            self.app_logger.info("Skipping BUY for %s: zero or negative available balance", asset.ticker_symbol)
            return

        trading_context = (
            self.session_manager.get_trading_context(asset.key)
            if self.session_manager else None
        )
        if trading_context is None and self.session_manager is not None:
            self.app_logger.debug("Skipping BUY for uninitialized context %s", asset.ticker_symbol)
            return

        regime_metrics = self._regime_detector.detect(candles, market_data)
        if trading_context:
            trading_context.regime = regime_metrics.regime.value
            trading_context.regime_volatility = regime_metrics.volatility
            trading_context.regime_trend_strength = regime_metrics.trend_strength
            trading_context.regime_liquidity = regime_metrics.liquidity
            trading_context.regime_spread = regime_metrics.spread
            if self.portfolio_risk_manager:
                risk_metrics = self.portfolio_risk_manager.get_risk_metrics(asset)
                trading_context.portfolio_total_exposure = float(risk_metrics.total_exposure_pct)
                trading_context.portfolio_drawdown = float(risk_metrics.drawdown_pct)
                trading_context.portfolio_cash = float(risk_metrics.available_cash)
                trading_context.portfolio_equity = float(risk_metrics.total_equity)

        if self.portfolio_risk_manager and trading_context:
            self.portfolio_risk_manager.update_position(asset, trading_context.position_qty)

        market_snapshot = self._build_market_snapshot(market_data, candles)
        regime_snapshot = self._build_regime_snapshot(regime_metrics)
        portfolio_snapshot = self._build_portfolio_snapshot(asset, trading_context)
        commit_hash = self.session_manager.get_current_commit_hash() if self.session_manager else None

        decision = self._evaluate_decision(asset, TradeAction.BUY, trading_context, market_data, candles)
        consensus_snapshot = self._build_consensus_snapshot(TradeAction.BUY, decision)

        if decision is None or not decision.quorum:
            self.app_logger.debug("No consensus to buy %s", asset.ticker_symbol)
            trading_decision = TradingDecision(
                ticker_symbol=asset.ticker_symbol,
                exchange=asset.exchange.value,
                trade_action=TradeAction.BUY,
                status=DecisionStatus.REJECTED,
                rejection_reason="NO_QUORUM",
                commit_hash=commit_hash,
                market_snapshot=market_snapshot,
                regime_snapshot=regime_snapshot,
                consensus_snapshot=consensus_snapshot,
                sizing_snapshot=SizingSnapshot(min_quantity=Decimal(str(asset.min_quantity))),
                portfolio_snapshot=portfolio_snapshot,
                risk_evaluation=RiskEvaluation(passed=False, rejection_reason="No consensus quorum"),
            )
            self._record_decision(trading_decision)
            return

        self.app_logger.info("Consensus reached to buy %s", asset.ticker_symbol)
        price = self._calculate_price(asset, market_data, fees)
        winning_strategy = self._resolve_winning_strategy(decision)

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
            trading_decision = TradingDecision(
                ticker_symbol=asset.ticker_symbol,
                exchange=asset.exchange.value,
                trade_action=TradeAction.BUY,
                status=DecisionStatus.SKIPPED,
                rejection_reason=DecisionRejectedReason.OUTSTANDING_INTENT.value,
                commit_hash=commit_hash,
                winning_strategy=winning_strategy,
                market_snapshot=market_snapshot,
                regime_snapshot=regime_snapshot,
                consensus_snapshot=consensus_snapshot,
                sizing_snapshot=SizingSnapshot(min_quantity=Decimal(str(asset.min_quantity))),
                portfolio_snapshot=portfolio_snapshot,
                risk_evaluation=RiskEvaluation(passed=True),
            )
            self._record_decision(trading_decision)
            return

        if not self._validate_execution_edge(asset, TradeAction.BUY, market_data, fees):
            trading_decision = TradingDecision(
                ticker_symbol=asset.ticker_symbol,
                exchange=asset.exchange.value,
                trade_action=TradeAction.BUY,
                status=DecisionStatus.REJECTED,
                rejection_reason=DecisionRejectedReason.NEGATIVE_EDGE.value,
                commit_hash=commit_hash,
                winning_strategy=winning_strategy,
                market_snapshot=market_snapshot,
                regime_snapshot=regime_snapshot,
                consensus_snapshot=consensus_snapshot,
                sizing_snapshot=SizingSnapshot(min_quantity=Decimal(str(asset.min_quantity))),
                portfolio_snapshot=portfolio_snapshot,
                risk_evaluation=RiskEvaluation(passed=False, rejection_reason="Negative execution edge after fees"),
            )
            self._record_decision(trading_decision)
            return

        quantity_val = self._calculate_quantity(
            asset, TradeAction.BUY, market_data, decision,
            candles=candles, regime=regime_metrics.regime
        )
        if quantity_val is None:
            return

        order_cost = price * quantity_val
        parser = self._get_dynamic_quantity_parser(asset)
        sizing_snapshot = SizingSnapshot(
            formula=parser.expression if parser else None,
            calculated_quantity=quantity_val,
            min_quantity=Decimal(str(asset.min_quantity)),
            final_quantity=quantity_val,
            variables={"order_cost": str(order_cost), "price": str(price)},
        )

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
            trading_decision = TradingDecision(
                ticker_symbol=asset.ticker_symbol,
                exchange=asset.exchange.value,
                trade_action=TradeAction.BUY,
                status=DecisionStatus.REJECTED,
                rejection_reason=DecisionRejectedReason.INSUFFICIENT_BALANCE.value,
                commit_hash=commit_hash,
                winning_strategy=winning_strategy,
                market_snapshot=market_snapshot,
                regime_snapshot=regime_snapshot,
                consensus_snapshot=consensus_snapshot,
                sizing_snapshot=sizing_snapshot,
                portfolio_snapshot=portfolio_snapshot,
                risk_evaluation=RiskEvaluation(passed=False, rejection_reason="Order cost exceeds available balance"),
            )
            self._record_decision(trading_decision)
            return

        if self.portfolio_risk_manager:
            can_trade, reject_reason = self.portfolio_risk_manager.can_trade(
                asset, TradeAction.BUY, order_cost, market_data, regime=regime_metrics.regime
            )
            if not can_trade:
                self._publish_event(DecisionRejectedEvent(
                    symbol=asset.ticker_symbol,
                    action=TradeAction.BUY.value,
                    reason=DecisionRejectedReason.RISK_REJECTED.value,
                    details={"reason": reject_reason},
                ))
                trading_decision = TradingDecision(
                    ticker_symbol=asset.ticker_symbol,
                    exchange=asset.exchange.value,
                    trade_action=TradeAction.BUY,
                    status=DecisionStatus.REJECTED,
                    rejection_reason=DecisionRejectedReason.RISK_REJECTED.value,
                    commit_hash=commit_hash,
                    winning_strategy=winning_strategy,
                    market_snapshot=market_snapshot,
                    regime_snapshot=regime_snapshot,
                    consensus_snapshot=consensus_snapshot,
                    sizing_snapshot=sizing_snapshot,
                    portfolio_snapshot=portfolio_snapshot,
                    risk_evaluation=RiskEvaluation(passed=False, rejection_reason=reject_reason),
                )
                self._record_decision(trading_decision)
                return

        health_eval = None
        if self.health_monitor is not None:
            asset_scope = HealthScope.asset_scope(asset.ticker_symbol)
            quote_portfolio_key = asset.quote_ticker_symbol
            allowed = self.health_monitor.has_permission(
                asset_scope,
                TradingPermission.NEW_ORDERS,
                exchange_name=asset.exchange.value,
                quote_portfolio_key=quote_portfolio_key,
            )
            snapshot = self.health_monitor.snapshot
            health_eval = HealthEvaluation(
                state=snapshot.state.value,
                allowed=allowed,
                active_conditions=[c.condition.value for c in snapshot.active_conditions],
            )
            if not allowed:
                self.app_logger.warning(
                    "Trading health blocked NEW_ORDERS for %s", asset.ticker_symbol
                )
                self._publish_event(DecisionRejectedEvent(
                    symbol=asset.ticker_symbol,
                    action=TradeAction.BUY.value,
                    reason=DecisionRejectedReason.HEALTH_HALT.value,
                    details={
                        "state": snapshot.state.value,
                        "active_conditions": [
                            c.condition.value for c in snapshot.active_conditions
                        ],
                    },
                ))
                trading_decision = TradingDecision(
                    ticker_symbol=asset.ticker_symbol,
                    exchange=asset.exchange.value,
                    trade_action=TradeAction.BUY,
                    status=DecisionStatus.REJECTED,
                    rejection_reason=DecisionRejectedReason.HEALTH_HALT.value,
                    commit_hash=commit_hash,
                    winning_strategy=winning_strategy,
                    market_snapshot=market_snapshot,
                    regime_snapshot=regime_snapshot,
                    consensus_snapshot=consensus_snapshot,
                    sizing_snapshot=sizing_snapshot,
                    portfolio_snapshot=portfolio_snapshot,
                    risk_evaluation=RiskEvaluation(passed=True),
                    health_evaluation=health_eval,
                )
                self._record_decision(trading_decision)
                return

        quantity = format(quantity_val, "f")
        trading_decision = TradingDecision(
            ticker_symbol=asset.ticker_symbol,
            exchange=asset.exchange.value,
            trade_action=TradeAction.BUY,
            status=DecisionStatus.EXECUTED,
            commit_hash=commit_hash,
            winning_strategy=winning_strategy,
            market_snapshot=market_snapshot,
            regime_snapshot=regime_snapshot,
            consensus_snapshot=consensus_snapshot,
            sizing_snapshot=sizing_snapshot,
            portfolio_snapshot=portfolio_snapshot,
            risk_evaluation=RiskEvaluation(passed=True),
            health_evaluation=health_eval,
        )
        self._submit_buy_order(asset, price, quantity, market_data, decision, trading_decision)

    def _submit_buy_order(
            self,
            asset: Asset,
            price: Decimal,
            quantity: str,
            market_data: MarketData,
            decision: ConsensusDecision,
            trading_decision: Optional[TradingDecision] = None,
    ) -> None:
        commit_hash = self.session_manager.get_current_commit_hash()
        winning_strategy = self._resolve_winning_strategy(decision)
        strategy_votes = self._format_strategy_votes(decision)
        decision_id = trading_decision.decision_id if trading_decision else None
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
            decision_id=decision_id,
        )
        if trading_decision:
            trading_decision.resulting_order_id = buy_order.uuid
            self._record_decision(trading_decision)

        if self.portfolio_risk_manager:
            self.portfolio_risk_manager.reserve_order_cash(
                asset, buy_order.uuid, price * Decimal(quantity)
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
            context=f'order_id={buy_order.uuid},price={price},quantity={quantity},commit_hash={commit_hash},decision_id={decision_id}'
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
            if not self.account_manager.init_asset_balance(asset):
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

        regime_metrics = self._regime_detector.detect(candles, market_data)
        market_snapshot = self._build_market_snapshot(market_data, candles)
        regime_snapshot = self._build_regime_snapshot(regime_metrics)
        portfolio_snapshot = self._build_portfolio_snapshot(asset, trading_context)
        commit_hash = self.session_manager.get_current_commit_hash() if self.session_manager else None

        decision = self._evaluate_decision(asset, TradeAction.SELL, trading_context, market_data, candles)
        consensus_snapshot = self._build_consensus_snapshot(TradeAction.SELL, decision)

        if decision is None or not decision.quorum:
            return

        winning_strategy = self._resolve_winning_strategy(decision)

        if not self._validate_execution_edge(asset, TradeAction.SELL, market_data, fees):
            trading_decision = TradingDecision(
                ticker_symbol=asset.ticker_symbol,
                exchange=asset.exchange.value,
                trade_action=TradeAction.SELL,
                status=DecisionStatus.REJECTED,
                rejection_reason=DecisionRejectedReason.NEGATIVE_EDGE.value,
                commit_hash=commit_hash,
                winning_strategy=winning_strategy,
                market_snapshot=market_snapshot,
                regime_snapshot=regime_snapshot,
                consensus_snapshot=consensus_snapshot,
                sizing_snapshot=SizingSnapshot(min_quantity=Decimal(str(asset.min_quantity))),
                portfolio_snapshot=portfolio_snapshot,
                risk_evaluation=RiskEvaluation(passed=False, rejection_reason="Negative execution edge after fees"),
            )
            self._record_decision(trading_decision)
            return

        quantity_val = self._calculate_quantity(
            asset, TradeAction.SELL, market_data, decision,
            candles=candles, regime=regime_metrics.regime
        )
        if quantity_val is None:
            return
        quantity = format(quantity_val, "f")
        sizing_snapshot = SizingSnapshot(
            calculated_quantity=quantity_val,
            min_quantity=Decimal(str(asset.min_quantity)),
            final_quantity=quantity_val,
            variables={"price": str(price)},
        )

        health_eval = None
        if self.health_monitor is not None:
            asset_scope = HealthScope.asset_scope(asset.ticker_symbol)
            quote_portfolio_key = asset.quote_ticker_symbol
            can_reduce = self.health_monitor.has_permission(
                asset_scope,
                TradingPermission.REDUCE_POSITIONS,
                exchange_name=asset.exchange.value,
                quote_portfolio_key=quote_portfolio_key,
            )
            can_close = self.health_monitor.has_permission(
                asset_scope,
                TradingPermission.CLOSE_POSITIONS,
                exchange_name=asset.exchange.value,
                quote_portfolio_key=quote_portfolio_key,
            )
            can_new = self.health_monitor.has_permission(
                asset_scope,
                TradingPermission.NEW_ORDERS,
                exchange_name=asset.exchange.value,
                quote_portfolio_key=quote_portfolio_key,
            )
            allowed = can_reduce or can_close or can_new
            snapshot = self.health_monitor.snapshot
            health_eval = HealthEvaluation(
                state=snapshot.state.value,
                allowed=allowed,
                active_conditions=[c.condition.value for c in snapshot.active_conditions],
            )
            if not allowed:
                self.app_logger.warning(
                    "Trading health blocked SELL for %s", asset.ticker_symbol
                )
                self._publish_event(DecisionRejectedEvent(
                    symbol=asset.ticker_symbol,
                    action=TradeAction.SELL.value,
                    reason=DecisionRejectedReason.HEALTH_HALT.value,
                    details={
                        "state": snapshot.state.value,
                        "active_conditions": [
                            c.condition.value for c in snapshot.active_conditions
                        ],
                    },
                ))
                trading_decision = TradingDecision(
                    ticker_symbol=asset.ticker_symbol,
                    exchange=asset.exchange.value,
                    trade_action=TradeAction.SELL,
                    status=DecisionStatus.REJECTED,
                    rejection_reason=DecisionRejectedReason.HEALTH_HALT.value,
                    commit_hash=commit_hash,
                    winning_strategy=winning_strategy,
                    market_snapshot=market_snapshot,
                    regime_snapshot=regime_snapshot,
                    consensus_snapshot=consensus_snapshot,
                    sizing_snapshot=sizing_snapshot,
                    portfolio_snapshot=portfolio_snapshot,
                    risk_evaluation=RiskEvaluation(passed=True),
                    health_evaluation=health_eval,
                )
                self._record_decision(trading_decision)
                return

        if base_balance.available_balance >= quantity_val:
            trading_decision = TradingDecision(
                ticker_symbol=asset.ticker_symbol,
                exchange=asset.exchange.value,
                trade_action=TradeAction.SELL,
                status=DecisionStatus.EXECUTED,
                commit_hash=commit_hash,
                winning_strategy=winning_strategy,
                market_snapshot=market_snapshot,
                regime_snapshot=regime_snapshot,
                consensus_snapshot=consensus_snapshot,
                sizing_snapshot=sizing_snapshot,
                portfolio_snapshot=portfolio_snapshot,
                risk_evaluation=RiskEvaluation(passed=True),
                health_evaluation=health_eval,
            )
            self._submit_sell_order(asset, price, quantity, market_data, decision, trading_decision)

    def _submit_sell_order(
            self,
            asset: Asset,
            price: Decimal,
            quantity: str,
            market_data: MarketData,
            decision: ConsensusDecision,
            trading_decision: Optional[TradingDecision] = None,
    ) -> None:
        commit_hash = self.session_manager.get_current_commit_hash()
        winning_strategy = self._resolve_winning_strategy(decision)
        strategy_votes = self._format_strategy_votes(decision)
        decision_id = trading_decision.decision_id if trading_decision else None
        sell_order = self.order_manager.open_order(
            price=price, trade_action=TradeAction.SELL,
            quantity=quantity, provider_name=asset.exchange.value,
            ticker_symbol=asset.ticker_symbol, timestamp=market_data.timestamp,
            commit_hash=commit_hash,
            winning_strategy=winning_strategy,
            strategy_votes=strategy_votes,
            decision_id=decision_id,
        )
        if trading_decision:
            trading_decision.resulting_order_id = sell_order.uuid
            self._record_decision(trading_decision)

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
            context=f'order_id={sell_order.uuid},price={price},quantity={quantity},commit_hash={commit_hash},decision_id={decision_id}'
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
        self.account_manager.close_account_balances()
        session = self.session_manager.end_session()
        if session:
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
            (
                name,
                decision.weights[name] if name in decision.weights else 1.0,
            )
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
            self,
            asset: Asset,
            _action: TradeAction,
            market_data: MarketData,
            decision: ConsensusDecision,
            candles: Optional[list[Candle]] = None,
            regime: Optional[MarketRegime] = None,
    ) -> Decimal:
        trading_context = self.session_manager.get_trading_context(asset.key)
        account_balance = self.account_manager.get_quote_balance(asset, asset.exchange.value)
        active_candles = candles if candles is not None else self.market_data_manager.get_candles(asset)
        active_regime = regime or self._regime_detector.detect(active_candles, market_data).regime
        risk_metrics = (
            self.portfolio_risk_manager.get_risk_metrics(asset)
            if self.portfolio_risk_manager
            else None
        )
        effective_config = None
        if self.portfolio_risk_manager and isinstance(self.portfolio_risk_manager.portfolio_config, PortfolioConfig):
            effective_config = PortfolioPolicyResolver.resolve(
                self.portfolio_risk_manager.portfolio_config,
                asset,
                regime=active_regime,
            )

        return self.position_sizer.calculate_quantity(
            asset=asset,
            market_data=market_data,
            decision=decision,
            account_balance=account_balance,
            trading_context=trading_context,
            candles=active_candles,
            risk_metrics=risk_metrics,
            effective_config=effective_config,
        )

