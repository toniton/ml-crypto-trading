from __future__ import annotations

from enum import Enum


class MetricName(str, Enum):
    # Trading & Order Lifecycle (Counters)
    ORDERS_SUBMITTED_TOTAL = "orders.submitted.total"
    ORDERS_FILLED_TOTAL = "orders.filled.total"
    ORDERS_CANCELLED_TOTAL = "orders.cancelled.total"
    ORDERS_REJECTED_TOTAL = "orders.rejected.total"
    TRADES_CLOSED_TOTAL = "trades.closed.total"
    PNL_REALIZED_TOTAL = "pnl.realized.total"
    FEES_PAID_TOTAL = "fees.paid.total"
    SLIPPAGE_COST_TOTAL = "slippage.cost.total"
    DECISIONS_TOTAL = "decisions.total"
    DECISIONS_REJECTED_TOTAL = "decisions.rejected.total"
    RISK_REJECTIONS_TOTAL = "risk.rejections.total"
    CONSENSUS_QUORUM_TOTAL = "consensus.quorum.total"
    POSITIONS_CHANGED_TOTAL = "positions.changed.total"
    EVALUATIONS_TOTAL = "evaluations.total"
    SIGNALS_TOTAL = "signals.total"

    # Trading Histograms
    TRADE_PNL = "trade.pnl"
    TRADE_RETURN_PCT = "trade.return_pct"
    TRADE_DURATION_SECONDS = "trade.duration_seconds"
    ORDER_LATENCY_SUBMIT = "order.latency.submit"
    ORDER_LATENCY_EXECUTION = "order.latency.execution"
    ORDER_LATENCY_TERMINAL = "order.latency.terminal"

    # Order Lifecycle Gauges
    ORDERS_PENDING = "orders.pending"
    ORDERS_PROCESSING = "orders.processing"
    ORDERS_RECONCILIATION_REQUIRED = "orders.reconciliation_required"
    ORDERS_UNKNOWN = "orders.unknown"
    ORDERS_STATE_MISMATCH = "orders.state_mismatch"
    ORDERS_STUCK_5M = "orders.stuck_5m"
    ORDERS_PENDING_GT_30S = "orders.pending_gt_30s"
    ORDERS_ORPHANED = "orders.orphaned"

    # Runtime & Incident Metrics
    RUNTIME_ERRORS_TOTAL = "runtime.errors.total"
    RUNTIME_INCIDENTS_TOTAL = "runtime.incidents.total"
    RUNTIME_INCIDENT_OCCURRENCES = "runtime.incident.occurrences"
    RUNTIME_UPTIME = "runtime.uptime"
    RUNTIME_MEMORY = "runtime.memory"
    RUNTIME_CPU = "runtime.cpu"
    RUNTIME_THREADS = "runtime.threads"
    RUNTIME_EVENT_LOOP_LAG = "runtime.event_loop_lag"
    RUNTIME_LAST_HEARTBEAT = "runtime.last_heartbeat"

    # Exchange & Inbound/Outbound HTTP Metrics
    EXCHANGE_REQUESTS = "exchange.requests"
    EXCHANGE_REQUEST_DURATION = "exchange.request.duration"
    EXCHANGE_ERRORS = "exchange.errors"
    CIRCUIT_BREAKER_TRIPPED = "circuit_breaker.tripped"
    EXCHANGE_WEBSOCKET_MESSAGES = "exchange.websocket.messages"
    EXCHANGE_WEBSOCKET_ERRORS = "exchange.websocket.errors"
    EXCHANGE_WEBSOCKET_RECONNECTS = "exchange.websocket.reconnects"
    HTTP_REQUESTS = "http.requests"
    HTTP_REQUEST_DURATION = "http.request.duration"
    HTTP_ERRORS = "http.errors"


class MetricLabelKey(str, Enum):
    SYMBOL = "symbol"
    EXCHANGE = "exchange"
    ACTION = "action"
    STRATEGY = "strategy"
    COMMIT_HASH = "commit_hash"
    REASON = "reason"
    QUORUM_MET = "quorum_met"
    DECISION = "decision"
    PROVIDER = "provider"
    OPERATION = "operation"
    ERROR_TYPE = "error_type"
    TYPE = "type"
    SEVERITY = "severity"
    CATEGORY = "category"
    COMPONENT = "component"


class MetricUnit(str, Enum):
    ORDERS = "orders"
    TRADES = "trades"
    CURRENCY = "currency"
    PERCENT = "percent"
    SECONDS = "seconds"
    MILLISECONDS = "ms"
    DECISIONS = "decisions"
    REJECTIONS = "rejections"
    EVALUATIONS = "evaluations"
    SIGNALS = "signals"
    EVENTS = "events"
    ERRORS = "errors"
    INCIDENTS = "incidents"
    OCCURRENCES = "occurrences"
    COUNT = "count"
    MEGABYTES = "MB"
    PERCENT_SIGN = "%"
    TIMESTAMP = "timestamp"


class FallbackValue(str, Enum):
    UNKNOWN = "UNKNOWN"
    ALL = "ALL"
    TRUE = "true"
    FALSE = "false"
