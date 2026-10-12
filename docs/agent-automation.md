# Agent Automation & Monitoring

This document describes the autonomous agent automation subsystem: how the bot detects trading
inactivity, decides what to do about it, and how the server stays a thin, agnostic transport layer.

## Design principle

> **Automation detects and decides; events communicate; projectors persist/read-model; the UI
> presents and requests decisions; VCS / Trading / Backtest services perform the approved operation.**

The event bus is the **application-level command/result channel between the server transport layer
and agent automation**. It is the boundary — not an event-sourcing mandate for every internal call.
Internal automation (`AutomationController → BacktestService / VCS / ConfigurationService`) remains
a normal domain call.

## Components

| Component | Location | Responsibility |
| :--- | :--- | :--- |
| `AssetActivityTracker` | `src/trading/activity/` | Subscribes to the trading event bus and records per-asset timestamps for market data, strategy evaluation, signals, order submission and execution. |
| `StarvationWatchdog` | `src/agent/monitoring/` | Polls activity; emits `TradingActivityAnomalyDetectedEvent` for silent assets. Never constructs actions. |
| `InvestigateActivityAnomaly` | `src/agent/automation/` | Deterministic (no LLM) classification: connectivity/data, strategy behaviour, risk/configuration, or exchange/order problems. |
| `AutomationController` | `src/agent/automation/` | Owns the worker queue, action planner, approvals and watchdog; enforces the safety authority. |
| `AgentEventProjector` | `src/server/` | Idempotent read-model builder; projects events into the conversation store and chat, and maintains action/approval read models. |
| `AutomationWorker` | `src/agent/automation/` | Single-consumer queue with explicit ordering, backpressure and shutdown semantics. |

## Event contract

All agent events carry a common envelope:

```python
request_id: UUID | None      # originating command (idempotency key at the automation boundary)
correlation_id: UUID          # the whole workflow
causation_id: UUID | None     # the event/incident that directly caused this event
sequence_number: int          # ordering within an aggregate
event_id: str                 # deduplication key for idempotent projection
```

### Server → automation (commands)

- `AgentActionPlanRequestedEvent` — plan/execute an action.
- `AgentApprovalDecisionRequestedEvent` — approve/reject a pending approval.

### Automation → server (facts)

- `AgentMessageCreatedEvent` — proactive chat message (e.g. a Drift Diagnostic).
- `AgentActionCreatedEvent / AgentActionUpdatedEvent / AgentActionCompletedEvent / AgentActionFailedEvent`
- `AgentApprovalRequestedEvent / AgentApprovalResolvedEvent` — the latter carries `error_code` /
  `error_message` for structured failures (`BASE_COMMIT_CHANGED`, `APPROVAL_EXPIRED`, `PROPOSAL_INVALID`, ...).
- `TradingActivityAnomalyDetectedEvent` — watchdog output.

## Safety classification

Every action belongs to one of:

```
INFORMATIONAL   (chat messages)
DIAGNOSTIC      (read-only analysis / backtests / drift detection)
PROPOSAL        (proposes a config change, requires approval to apply)
STATE_CHANGING  (writes to VCS / applies configuration)
TRADING_CONTROL (places/cancels orders)
```

Autonomous monitors default to `{INFORMATIONAL, DIAGNOSTIC, PROPOSAL}`; **state-changing and
trading-control are prohibited unless explicitly granted**.

## Autonomous workflow

```
Watchdog detects inactivity
   │  TradingActivityAnomalyDetectedEvent
   ▼
InvestigateActivityAnomaly            # deterministic, no LLM
   ▼
Automation decision
   ├── Send Drift Diagnostic chat message           (INFORMATIONAL)
   ├── Raise an Approval Proposal to pause the asset (PROPOSAL)
   └── escalate to a runtime incident
   │
   ▼
VCS / Backtest perform the approved operation
```

## REST & WebSocket

See the README's *Agent REST endpoints* table. Commands return `202 Accepted` with a `request_id`;
the final outcome is delivered over `/api/v1/agent/ws` as `agent_*` events. The projector,
which is idempotent per `event_id`, materialises results into the conversation store and the
action/approval read models.