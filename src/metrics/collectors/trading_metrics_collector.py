from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import threading
from typing import Any, Optional

from api.interfaces.trade import Trade
from api.interfaces.trade_action import TradeAction
from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.events.message_event_bus import CallbackSubscription
from src.metrics.models.metric_type import AggregationType, MetricType
from src.metrics.services.metric_service import MetricService
from src.trading.events import (
    ConsensusEvaluatedEvent,
    DecisionRejectedEvent,
    OrderFilledEvent,
    OrderSubmittedEvent,
    PositionChangedEvent,
    SignalGeneratedEvent,
    StrategyEvaluatedEvent,
    TradeClosedEvent,
)


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
    """Collects trading decision funnel telemetry and performance metrics from the event bus."""

    def __init__(self, metric_service: MetricService):
        self._metric_service = metric_service
        self._lock = threading.Lock()
        self._funnel_by_symbol: dict[str, FunnelCounts] = defaultdict(FunnelCounts)
        self._closed_trades: list[Trade] = []
        self._subscription_ids: list[str] = []
        self._register_definitions()

    def _register_definitions(self) -> None:
        self._metric_service.register(
            "trading.evaluations.total",
            metric_type=MetricType.COUNTER,
            unit="evaluations",
            description="Total market evaluations executed",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            "trading.signals.total",
            metric_type=MetricType.COUNTER,
            unit="signals",
            description="Total trading signals generated",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            "trading.consensus.passed.total",
            metric_type=MetricType.COUNTER,
            unit="decisions",
            description="Total consensus decisions reaching quorum",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            "trading.decisions.rejected.total",
            metric_type=MetricType.COUNTER,
            unit="rejections",
            description="Total decisions rejected at any funnel stage",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            "trading.orders.submitted.total",
            metric_type=MetricType.COUNTER,
            unit="orders",
            description="Total orders submitted to execution layer",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            "trading.orders.filled.total",
            metric_type=MetricType.COUNTER,
            unit="orders",
            description="Total orders filled by exchange",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            "trading.positions.changed.total",
            metric_type=MetricType.COUNTER,
            unit="events",
            description="Total position state changes",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            "trading.trades.closed.total",
            metric_type=MetricType.COUNTER,
            unit="trades",
            description="Total closed round-trip trades",
            aggregation=AggregationType.SUM,
        )
        self._metric_service.register(
            "trading.trade.pnl",
            metric_type=MetricType.HISTOGRAM,
            unit="currency",
            description="Net P&L distribution of closed trades",
            aggregation=AggregationType.P95,
        )
        self._metric_service.register(
            "trading.trade.return_pct",
            metric_type=MetricType.HISTOGRAM,
            unit="percent",
            description="Return percentage distribution of closed trades",
            aggregation=AggregationType.P95,
        )
        self._metric_service.register(
            "trading.trade.duration_seconds",
            metric_type=MetricType.HISTOGRAM,
            unit="seconds",
            description="Holding duration of closed trades",
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
        elif isinstance(event, PositionChangedEvent):
            self._handle_position_changed(event)
        elif isinstance(event, TradeClosedEvent):
            self._handle_trade_closed(event)

    def _handle_strategy_evaluated(self, event: StrategyEvaluatedEvent) -> None:
        with self._lock:
            self._funnel_by_symbol[event.symbol].evaluations += 1
        self._metric_service.increment("trading.evaluations.total", labels={"symbol": event.symbol})
        self._metric_service.flush()

    def _handle_signal_generated(self, event: SignalGeneratedEvent) -> None:
        with self._lock:
            self._funnel_by_symbol[event.symbol].signals += 1
        self._metric_service.increment(
            "trading.signals.total",
            labels={"symbol": event.symbol, "action": event.action},
        )
        self._metric_service.flush()

    def _handle_consensus_evaluated(self, event: ConsensusEvaluatedEvent) -> None:
        if event.quorum_met:
            with self._lock:
                self._funnel_by_symbol[event.symbol].consensus_passed += 1
            self._metric_service.increment(
                "trading.consensus.passed.total",
                labels={"symbol": event.symbol, "decision": event.decision},
            )
            self._metric_service.flush()

    def _handle_decision_rejected(self, event: DecisionRejectedEvent) -> None:
        with self._lock:
            self._funnel_by_symbol[event.symbol].rejections[event.reason] += 1
        self._metric_service.increment(
            "trading.decisions.rejected.total",
            labels={"symbol": event.symbol, "action": event.action, "reason": event.reason},
        )
        self._metric_service.flush()

    def _handle_order_submitted(self, event: OrderSubmittedEvent) -> None:
        action = (
            event.order.trade_action.value
            if isinstance(event.order.trade_action, TradeAction)
            else str(event.order.trade_action)
        )
        with self._lock:
            self._funnel_by_symbol[event.symbol].orders_submitted += 1
        self._metric_service.increment(
            "trading.orders.submitted.total",
            labels={"symbol": event.symbol, "action": action, "provider": str(event.order.provider_name)},
        )
        self._metric_service.flush()

    def _handle_order_filled(self, event: OrderFilledEvent) -> None:
        action = (
            event.order.trade_action.value
            if isinstance(event.order.trade_action, TradeAction)
            else str(event.order.trade_action)
        )
        with self._lock:
            self._funnel_by_symbol[event.symbol].orders_filled += 1
        self._metric_service.increment(
            "trading.orders.filled.total",
            labels={"symbol": event.symbol, "action": action, "provider": str(event.order.provider_name)},
        )
        self._metric_service.flush()

    def _handle_position_changed(self, event: PositionChangedEvent) -> None:
        self._metric_service.increment(
            "trading.positions.changed.total",
            labels={"symbol": event.symbol, "action": event.action},
        )
        self._metric_service.flush()

    def _handle_trade_closed(self, event: TradeClosedEvent) -> None:
        trade = event.trade
        with self._lock:
            self._funnel_by_symbol[event.symbol].trades_closed += 1
            self._closed_trades.append(trade)

        commit = trade.commit_hash or "UNKNOWN"
        winning = trade.winning_strategy or "UNKNOWN"
        labels = {"symbol": event.symbol, "commit_hash": commit, "winning_strategy": winning}

        self._metric_service.increment("trading.trades.closed.total", labels=labels)
        self._metric_service.observe("trading.trade.pnl", float(trade.net_pnl), labels=labels)
        self._metric_service.observe("trading.trade.return_pct", float(trade.return_pct), labels=labels)
        self._metric_service.observe("trading.trade.duration_seconds", trade.duration_seconds, labels=labels)
        self._metric_service.flush()

    def get_funnel_snapshot(self, symbol: Optional[str] = None) -> dict[str, Any]:
        counts, rejections = self._aggregate_funnel_counts(symbol)
        conversion_rates = self._compute_conversion_rates(counts)

        return {
            "symbol": symbol or "ALL",
            "evaluations": counts.evaluations,
            "signals": counts.signals,
            "consensus_passed": counts.consensus_passed,
            "orders_submitted": counts.orders_submitted,
            "orders_filled": counts.orders_filled,
            "trades_closed": counts.trades_closed,
            "rejections": rejections,
            "conversion_rates": conversion_rates,
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
            "eval_to_signal_pct": round(eval_to_signal, 2),
            "signal_to_submit_pct": round(signal_to_submit, 2),
            "submit_to_fill_pct": round(submit_to_fill, 2),
            "eval_to_fill_pct": round(eval_to_fill, 2),
        }

    def get_closed_trades(self, symbol: Optional[str] = None) -> list[Trade]:
        with self._lock:
            if symbol is not None:
                return [t for t in self._closed_trades if t.ticker_symbol == symbol]
            return list(self._closed_trades)
