from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
import threading
from typing import Any, Optional

from api.interfaces.order import Order
from api.interfaces.trade import Trade
from api.interfaces.trade_action import TradeAction
from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.events.message_event_bus import CallbackSubscription
from src.metrics.models.constants import (
    FallbackValue,
    MetricLabelKey,
    MetricName,
    MetricUnit,
)
from src.metrics.models.metric_type import AggregationType, MetricType
from src.metrics.services.metric_service import MetricService
from src.trading.events import (
    ConsensusEvaluatedEvent,
    DecisionRejectedEvent,
    DecisionRejectedReason,
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderRejectedEvent,
    OrderSubmittedEvent,
    PositionChangedEvent,
    SignalGeneratedEvent,
    StrategyEvaluatedEvent,
    TradeClosedEvent,
)

_RISK_REJECTION_REASONS: set[str] = {
    DecisionRejectedReason.RISK_REJECTED.value,
    DecisionRejectedReason.GUARD_HALT.value,
    DecisionRejectedReason.BELOW_MIN_QUANTITY.value,
    DecisionRejectedReason.INSUFFICIENT_BALANCE.value,
    DecisionRejectedReason.NEGATIVE_EDGE.value,
    DecisionRejectedReason.QUANTITY_CALCULATION_FAILED.value,
}


class FunnelSnapshotKey(str, Enum):
    SYMBOL = "symbol"
    EVALUATIONS = "evaluations"
    SIGNALS = "signals"
    CONSENSUS_PASSED = "consensus_passed"
    ORDERS_SUBMITTED = "orders_submitted"
    ORDERS_FILLED = "orders_filled"
    TRADES_CLOSED = "trades_closed"
    REJECTIONS = "rejections"
    CONVERSION_RATES = "conversion_rates"


class ConversionRateKey(str, Enum):
    EVAL_TO_SIGNAL_PCT = "eval_to_signal_pct"
    SIGNAL_TO_SUBMIT_PCT = "signal_to_submit_pct"
    SUBMIT_TO_FILL_PCT = "submit_to_fill_pct"
    EVAL_TO_FILL_PCT = "eval_to_fill_pct"


@dataclass
class FunnelCounts:
    evaluations: int = 0
    signals: int = 0
    consensus_passed: int = 0
    orders_submitted: int = 0
    orders_filled: int = 0
    trades_closed: int = 0
    rejections: dict[str, int] = field(default_factory=lambda: defaultdict(int))


class TradingMetricsCollector:
    """Collects canonical trading metrics and decision funnel telemetry from the event bus."""

    def __init__(self, metric_service: MetricService):
        self._metric_service = metric_service
        self._lock = threading.Lock()
        self._funnel_by_symbol: dict[str, FunnelCounts] = defaultdict(FunnelCounts)
        self._closed_trades: list[Trade] = []
        self._subscription_ids: list[str] = []
        self._register_definitions()

    def _register_definitions(self) -> None:
        self._metric_service.register(
            MetricName.EVALUATIONS_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.EVALUATIONS.value,
            description="Total market evaluations executed",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.SIGNALS_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.SIGNALS.value,
            description="Total trading signals generated",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.DECISIONS_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.DECISIONS.value,
            description="Total candidate decisions / evaluations",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.CONSENSUS_QUORUM_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.DECISIONS.value,
            description="Total consensus decisions reaching quorum",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.DECISIONS_REJECTED_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.REJECTIONS.value,
            description="Total decisions rejected at any funnel stage",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.RISK_REJECTIONS_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.REJECTIONS.value,
            description="Total trade decisions rejected by risk checks or guards",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.ORDERS_SUBMITTED_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.ORDERS.value,
            description="Total orders submitted to execution layer",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.ORDERS_FILLED_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.ORDERS.value,
            description="Total orders filled by exchange",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.ORDERS_CANCELLED_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.ORDERS.value,
            description="Total orders cancelled",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.ORDERS_REJECTED_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.ORDERS.value,
            description="Total orders rejected by exchange",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.POSITIONS_CHANGED_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.EVENTS.value,
            description="Total position state changes",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.TRADES_CLOSED_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.TRADES.value,
            description="Total closed round-trip trades",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.PNL_REALIZED_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.CURRENCY.value,
            description="Cumulative realized net P&L",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.FEES_PAID_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.CURRENCY.value,
            description="Cumulative trading fees paid",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.SLIPPAGE_COST_TOTAL.value,
            metric_type=MetricType.COUNTER,
            unit=MetricUnit.CURRENCY.value,
            description="Cumulative slippage execution cost",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            MetricName.TRADE_PNL.value,
            metric_type=MetricType.HISTOGRAM,
            unit=MetricUnit.CURRENCY.value,
            description="Net P&L distribution of closed trades",
            aggregation=AggregationType.P95,
        )
        self._metric_service.register(
            MetricName.TRADE_RETURN_PCT.value,
            metric_type=MetricType.HISTOGRAM,
            unit=MetricUnit.PERCENT.value,
            description="Return percentage distribution of closed trades",
            aggregation=AggregationType.P95,
        )
        self._metric_service.register(
            MetricName.TRADE_DURATION_SECONDS.value,
            metric_type=MetricType.HISTOGRAM,
            unit=MetricUnit.SECONDS.value,
            description="Holding duration of closed trades",
            aggregation=AggregationType.P95,
        )
        self._metric_service.register(
            MetricName.ORDER_LATENCY_SUBMIT.value,
            metric_type=MetricType.HISTOGRAM,
            unit=MetricUnit.MILLISECONDS.value,
            description="Signal to order submit latency in ms",
            aggregation=AggregationType.P95,
        )
        self._metric_service.register(
            MetricName.ORDER_LATENCY_EXECUTION.value,
            metric_type=MetricType.HISTOGRAM,
            unit=MetricUnit.MILLISECONDS.value,
            description="Order submit to fill execution latency in ms",
            aggregation=AggregationType.P95,
        )
        self._metric_service.register(
            MetricName.ORDER_LATENCY_TERMINAL.value,
            metric_type=MetricType.HISTOGRAM,
            unit=MetricUnit.MILLISECONDS.value,
            description="Order submit to terminal state latency in ms",
            aggregation=AggregationType.P95,
        )

    def subscribe(self, event_bus: EventBus) -> list[str]:
        event_types = [
            StrategyEvaluatedEvent.__name__,
            SignalGeneratedEvent.__name__,
            ConsensusEvaluatedEvent.__name__,
            DecisionRejectedEvent.__name__,
            OrderSubmittedEvent.__name__,
            OrderFilledEvent.__name__,
            OrderCancelledEvent.__name__,
            OrderRejectedEvent.__name__,
            PositionChangedEvent.__name__,
            TradeClosedEvent.__name__,
        ]
        for event_type in event_types:
            sub_id = event_bus.subscribe(event_type, CallbackSubscription(self.on_event))
            self._subscription_ids.append(sub_id)
        return self._subscription_ids

    def on_event(self, event: Event) -> None:
        if isinstance(event, StrategyEvaluatedEvent):
            self._handle_strategy_evaluated(event)
        elif isinstance(event, SignalGeneratedEvent):
            self._handle_signal_generated(event)
        elif isinstance(event, ConsensusEvaluatedEvent):
            self._handle_consensus_evaluated(event)
        elif isinstance(event, DecisionRejectedEvent):
            self._handle_decision_rejected(event)
        elif isinstance(event, OrderSubmittedEvent):
            self._handle_order_submitted(event)
        elif isinstance(event, OrderFilledEvent):
            self._handle_order_filled(event)
        elif isinstance(event, OrderCancelledEvent):
            self._handle_order_cancelled(event)
        elif isinstance(event, OrderRejectedEvent):
            self._handle_order_rejected(event)
        elif isinstance(event, PositionChangedEvent):
            self._handle_position_changed(event)
        elif isinstance(event, TradeClosedEvent):
            self._handle_trade_closed(event)

    def _handle_strategy_evaluated(self, event: StrategyEvaluatedEvent) -> None:
        with self._lock:
            self._funnel_by_symbol[event.symbol].evaluations += 1
        commit = event.commit_hash or FallbackValue.UNKNOWN.value
        strategy = event.strategy_name or FallbackValue.UNKNOWN.value
        labels = {
            MetricLabelKey.SYMBOL.value: event.symbol,
            MetricLabelKey.STRATEGY.value: str(strategy),
            MetricLabelKey.COMMIT_HASH.value: str(commit),
        }
        self._metric_service.increment(MetricName.EVALUATIONS_TOTAL.value, labels=labels)
        self._metric_service.flush()

    def _handle_signal_generated(self, event: SignalGeneratedEvent) -> None:
        with self._lock:
            self._funnel_by_symbol[event.symbol].signals += 1
        commit = event.commit_hash or FallbackValue.UNKNOWN.value
        strategy = event.strategy_name or FallbackValue.UNKNOWN.value
        labels = {
            MetricLabelKey.SYMBOL.value: event.symbol,
            MetricLabelKey.ACTION.value: event.action,
            MetricLabelKey.STRATEGY.value: str(strategy),
            MetricLabelKey.COMMIT_HASH.value: str(commit),
        }
        self._metric_service.increment(MetricName.SIGNALS_TOTAL.value, labels=labels)
        self._metric_service.flush()

    def _handle_consensus_evaluated(self, event: ConsensusEvaluatedEvent) -> None:
        commit = event.commit_hash or FallbackValue.UNKNOWN.value
        exchange = event.exchange or FallbackValue.UNKNOWN.value
        labels = {
            MetricLabelKey.SYMBOL.value: event.symbol,
            MetricLabelKey.EXCHANGE.value: str(exchange),
            MetricLabelKey.ACTION.value: event.decision,
            MetricLabelKey.COMMIT_HASH.value: str(commit),
        }
        self._metric_service.increment(MetricName.DECISIONS_TOTAL.value, labels=labels)
        if event.quorum_met:
            with self._lock:
                self._funnel_by_symbol[event.symbol].consensus_passed += 1
            quorum_labels = dict(labels)
            quorum_labels[MetricLabelKey.QUORUM_MET.value] = FallbackValue.TRUE.value
            self._metric_service.increment(MetricName.CONSENSUS_QUORUM_TOTAL.value, labels=quorum_labels)
        self._metric_service.flush()

    def _handle_decision_rejected(self, event: DecisionRejectedEvent) -> None:
        with self._lock:
            self._funnel_by_symbol[event.symbol].rejections[event.reason] += 1

        exchange = (
            event.exchange
            or (event.details[MetricLabelKey.EXCHANGE.value] if MetricLabelKey.EXCHANGE.value in event.details else FallbackValue.UNKNOWN.value)
        )
        strategy = (
            event.details[MetricLabelKey.STRATEGY.value]
            if MetricLabelKey.STRATEGY.value in event.details
            else FallbackValue.UNKNOWN.value
        )
        commit = (
            event.commit_hash
            or (event.details[MetricLabelKey.COMMIT_HASH.value] if MetricLabelKey.COMMIT_HASH.value in event.details else FallbackValue.UNKNOWN.value)
        )
        labels = {
            MetricLabelKey.SYMBOL.value: event.symbol,
            MetricLabelKey.EXCHANGE.value: str(exchange),
            MetricLabelKey.ACTION.value: event.action,
            MetricLabelKey.STRATEGY.value: str(strategy),
            MetricLabelKey.COMMIT_HASH.value: str(commit),
            MetricLabelKey.REASON.value: event.reason,
        }
        self._metric_service.increment(MetricName.DECISIONS_REJECTED_TOTAL.value, labels=labels)
        if (
            event.reason in _RISK_REJECTION_REASONS
            or "RISK" in event.reason.upper()
            or "GUARD" in event.reason.upper()
            or "LIMIT" in event.reason.upper()
        ):
            self._metric_service.increment(MetricName.RISK_REJECTIONS_TOTAL.value, labels=labels)
        self._metric_service.flush()

    def _handle_order_submitted(self, event: OrderSubmittedEvent) -> None:
        labels = self._extract_order_labels(event)
        with self._lock:
            self._funnel_by_symbol[event.symbol].orders_submitted += 1
        self._metric_service.increment(MetricName.ORDERS_SUBMITTED_TOTAL.value, labels=labels)
        self._metric_service.flush()

    def _handle_order_filled(self, event: OrderFilledEvent) -> None:
        labels = self._extract_order_labels(event)
        with self._lock:
            self._funnel_by_symbol[event.symbol].orders_filled += 1
        self._metric_service.increment(MetricName.ORDERS_FILLED_TOTAL.value, labels=labels)
        self._record_order_latency(event.order, is_fill=True, is_terminal=True, labels=labels)
        self._metric_service.flush()

    def _handle_order_cancelled(self, event: OrderCancelledEvent) -> None:
        labels = self._extract_order_labels(event)
        self._metric_service.increment(MetricName.ORDERS_CANCELLED_TOTAL.value, labels=labels)
        self._record_order_latency(event.order, is_terminal=True, labels=labels)
        self._metric_service.flush()

    def _handle_order_rejected(self, event: OrderRejectedEvent) -> None:
        labels = self._extract_order_labels(event)
        labels[MetricLabelKey.REASON.value] = event.reason or FallbackValue.UNKNOWN.value
        self._metric_service.increment(MetricName.ORDERS_REJECTED_TOTAL.value, labels=labels)
        self._record_order_latency(event.order, is_terminal=True, labels=labels)
        self._metric_service.flush()

    def _handle_position_changed(self, event: PositionChangedEvent) -> None:
        commit = event.commit_hash or FallbackValue.UNKNOWN.value
        exchange = event.exchange or FallbackValue.UNKNOWN.value
        labels = {
            MetricLabelKey.SYMBOL.value: event.symbol,
            MetricLabelKey.EXCHANGE.value: str(exchange),
            MetricLabelKey.ACTION.value: event.action,
            MetricLabelKey.COMMIT_HASH.value: str(commit),
        }
        self._metric_service.increment(MetricName.POSITIONS_CHANGED_TOTAL.value, labels=labels)
        self._metric_service.flush()

    def _handle_trade_closed(self, event: TradeClosedEvent) -> None:
        trade = event.trade
        with self._lock:
            self._funnel_by_symbol[event.symbol].trades_closed += 1
            self._closed_trades.append(trade)

        exchange = event.exchange or FallbackValue.UNKNOWN.value
        commit = trade.commit_hash or event.commit_hash or FallbackValue.UNKNOWN.value
        strategy = trade.winning_strategy or FallbackValue.UNKNOWN.value
        labels = {
            MetricLabelKey.SYMBOL.value: event.symbol or trade.ticker_symbol,
            MetricLabelKey.EXCHANGE.value: str(exchange),
            MetricLabelKey.STRATEGY.value: str(strategy),
            MetricLabelKey.COMMIT_HASH.value: str(commit),
        }

        self._metric_service.increment(MetricName.TRADES_CLOSED_TOTAL.value, labels=labels)
        self._metric_service.increment(MetricName.PNL_REALIZED_TOTAL.value, float(trade.net_pnl), labels=labels)
        self._metric_service.increment(MetricName.FEES_PAID_TOTAL.value, float(trade.fees), labels=labels)
        self._metric_service.increment(MetricName.SLIPPAGE_COST_TOTAL.value, float(trade.slippage), labels=labels)

        self._metric_service.observe(MetricName.TRADE_PNL.value, float(trade.net_pnl), labels=labels)
        self._metric_service.observe(MetricName.TRADE_RETURN_PCT.value, float(trade.return_pct), labels=labels)
        self._metric_service.observe(MetricName.TRADE_DURATION_SECONDS.value, trade.duration_seconds, labels=labels)
        self._metric_service.flush()

    @staticmethod
    def _extract_order_labels(
            event: OrderSubmittedEvent | OrderFilledEvent | OrderCancelledEvent | OrderRejectedEvent,
    ) -> dict[str, str]:
        order = event.order
        action = (
            order.trade_action.value
            if isinstance(order.trade_action, TradeAction)
            else str(order.trade_action)
        )
        exchange = order.provider_name or event.exchange or FallbackValue.UNKNOWN.value
        strategy = order.winning_strategy or FallbackValue.UNKNOWN.value
        commit = order.commit_hash or event.commit_hash or FallbackValue.UNKNOWN.value
        return {
            MetricLabelKey.SYMBOL.value: event.symbol or order.ticker_symbol,
            MetricLabelKey.EXCHANGE.value: str(exchange),
            MetricLabelKey.ACTION.value: str(action),
            MetricLabelKey.STRATEGY.value: str(strategy),
            MetricLabelKey.COMMIT_HASH.value: str(commit),
        }

    def _record_order_latency(
            self,
            order: Order,
            is_fill: bool = False,
            is_terminal: bool = False,
            labels: Optional[dict[str, str]] = None,
    ) -> None:
        created_time = order.created_time
        executed_time = order.executed_time
        if created_time is not None and executed_time is not None and executed_time >= created_time:
            latency_ms = (executed_time - created_time) * 1000.0
            if is_fill:
                self._metric_service.observe(MetricName.ORDER_LATENCY_EXECUTION.value, latency_ms, labels=labels)
            if is_terminal:
                self._metric_service.observe(MetricName.ORDER_LATENCY_TERMINAL.value, latency_ms, labels=labels)

    def get_funnel_snapshot(self, symbol: Optional[str] = None) -> dict[str, Any]:
        counts, rejections = self._aggregate_funnel_counts(symbol)
        conversion_rates = self._compute_conversion_rates(counts)

        return {
            FunnelSnapshotKey.SYMBOL.value: symbol or FallbackValue.ALL.value,
            FunnelSnapshotKey.EVALUATIONS.value: counts.evaluations,
            FunnelSnapshotKey.SIGNALS.value: counts.signals,
            FunnelSnapshotKey.CONSENSUS_PASSED.value: counts.consensus_passed,
            FunnelSnapshotKey.ORDERS_SUBMITTED.value: counts.orders_submitted,
            FunnelSnapshotKey.ORDERS_FILLED.value: counts.orders_filled,
            FunnelSnapshotKey.TRADES_CLOSED.value: counts.trades_closed,
            FunnelSnapshotKey.REJECTIONS.value: rejections,
            FunnelSnapshotKey.CONVERSION_RATES.value: conversion_rates,
        }

    def _aggregate_funnel_counts(self, symbol: Optional[str]) -> tuple[FunnelCounts, dict[str, int]]:
        with self._lock:
            if symbol is not None:
                counts = self._funnel_by_symbol.get(symbol, FunnelCounts())
                return counts, dict(counts.rejections)

            aggregated = FunnelCounts(
                evaluations=sum(c.evaluations for c in self._funnel_by_symbol.values()),
                signals=sum(c.signals for c in self._funnel_by_symbol.values()),
                consensus_passed=sum(c.consensus_passed for c in self._funnel_by_symbol.values()),
                orders_submitted=sum(c.orders_submitted for c in self._funnel_by_symbol.values()),
                orders_filled=sum(c.orders_filled for c in self._funnel_by_symbol.values()),
                trades_closed=sum(c.trades_closed for c in self._funnel_by_symbol.values()),
            )
            rejections_dict: dict[str, int] = defaultdict(int)
            for c in self._funnel_by_symbol.values():
                for reason, count in c.rejections.items():
                    rejections_dict[reason] += count
            return aggregated, dict(rejections_dict)

    @staticmethod
    def _compute_conversion_rates(counts: FunnelCounts) -> dict[str, float]:
        eval_to_signal = (counts.signals / counts.evaluations * 100.0) if counts.evaluations > 0 else 0.0
        signal_to_submit = (
            (counts.orders_submitted / counts.signals * 100.0)
            if counts.signals > 0
            else 0.0
        )
        submit_to_fill = (
            (counts.orders_filled / counts.orders_submitted * 100.0)
            if counts.orders_submitted > 0
            else 0.0
        )
        eval_to_fill = (counts.orders_filled / counts.evaluations * 100.0) if counts.evaluations > 0 else 0.0

        return {
            ConversionRateKey.EVAL_TO_SIGNAL_PCT.value: round(eval_to_signal, 2),
            ConversionRateKey.SIGNAL_TO_SUBMIT_PCT.value: round(signal_to_submit, 2),
            ConversionRateKey.SUBMIT_TO_FILL_PCT.value: round(submit_to_fill, 2),
            ConversionRateKey.EVAL_TO_FILL_PCT.value: round(eval_to_fill, 2),
        }

    def get_closed_trades(self, symbol: Optional[str] = None) -> list[Trade]:
        with self._lock:
            if symbol is not None:
                return [t for t in self._closed_trades if t.ticker_symbol == symbol]
            return list(self._closed_trades)
