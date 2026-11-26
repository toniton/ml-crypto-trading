from __future__ import annotations

import time
from typing import Callable

from src.agent.automation.experiment_completion_handler import (
    ExperimentCompletionAgentHandler,
)
from src.core.hooks import HookCatalog, HookContext, HookManager, HookStage
from src.core.interfaces.conversation_store import RESERVED_AGENT_SESSION_ID
from src.events.decision_models import AgentDecisionRecordedEvent
from src.events.message_event_bus import CallbackSubscription, MessageEventBus
from src.server.agent_event_projector import AgentEventProjector
from tests.unit.agent.fakes import FakeConversationStore


def _wait_for(predicate: Callable, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        val = predicate()
        if val:
            return val
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for hook handler output")


def test_completed_experiment_posts_summary_and_records_decision():
    bus = MessageEventBus()
    store = FakeConversationStore()
    projector = AgentEventProjector(event_bus=bus, conversation_store=store)
    projector.subscribe()

    decisions: list[AgentDecisionRecordedEvent] = []
    bus.subscribe(
        AgentDecisionRecordedEvent.EVENT_TYPE,
        CallbackSubscription(decisions.append),
    )

    hook_manager = HookManager(max_workers=2)
    handler = ExperimentCompletionAgentHandler(event_bus=bus)
    handler.register(hook_manager)

    try:
        hook_manager.emit(
            HookContext(
                hook_name=HookCatalog.EXPERIMENT_RUN,
                stage=HookStage.COMPLETED,
                source_id="exp_btc_001",
                state="COMPLETED",
                payload={
                    "experiment_id": "exp_btc_001",
                    "name": "Anomaly BTC_USD (no-signals-drift)",
                    "ticker_symbol": "BTC_USD",
                    "status": "COMPLETED",
                    "report": {
                        "candidates": {
                            "cand_current": {
                                "name": "Current Configuration (Baseline)",
                                "backtest": {
                                    "total_trades": 0,
                                    "net_pnl": 0.0,
                                    "win_rate_pct": 0.0,
                                    "profit_factor": 0.0,
                                },
                            },
                            "cand_additional_strategies": {
                                "name": "Add Complementary Strategies",
                                "backtest": {
                                    "total_trades": 6,
                                    "net_pnl": 145.5,
                                    "win_rate_pct": 66.7,
                                    "profit_factor": 2.1,
                                },
                            },
                        }
                    },
                },
            )
        )

        message = _wait_for(
            lambda: (
                store.messages(RESERVED_AGENT_SESSION_ID)[0]
                if store.messages(RESERVED_AGENT_SESSION_ID)
                else None
            )
        )
        assert "Experiment completed — BTC_USD" in message.content
        assert "broke signal starvation" in message.content
        assert "Add Complementary Strategies" in message.content
        assert len(decisions) == 1
        assert decisions[0].decision.parameters["best_candidate_id"] == (
            "cand_additional_strategies"
        )
    finally:
        hook_manager.close(wait=True)
        projector.close()


def test_failed_experiment_notifies_agent_feed_with_warning():
    bus = MessageEventBus()
    store = FakeConversationStore()
    projector = AgentEventProjector(event_bus=bus, conversation_store=store)
    projector.subscribe()

    hook_manager = HookManager(max_workers=2)
    handler = ExperimentCompletionAgentHandler(event_bus=bus)
    handler.register(hook_manager)

    try:
        hook_manager.emit(
            HookContext(
                hook_name=HookCatalog.EXPERIMENT_RUN,
                stage=HookStage.FAILED,
                source_id="exp_fail_1",
                state="FAILED",
                error="All candidates failed during backtest",
                payload={
                    "experiment_id": "exp_fail_1",
                    "name": "Anomaly ETH_USD",
                    "ticker_symbol": "ETH_USD",
                    "status": "FAILED",
                },
            )
        )

        message = _wait_for(
            lambda: (
                store.messages(RESERVED_AGENT_SESSION_ID)[0]
                if store.messages(RESERVED_AGENT_SESSION_ID)
                else None
            )
        )
        assert "Experiment failed — ETH_USD" in message.content
        assert "All candidates failed during backtest" in message.content
        assert message.payload["notification"]["severity"] == "WARNING"
    finally:
        hook_manager.close(wait=True)
        projector.close()
