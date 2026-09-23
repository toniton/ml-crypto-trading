from __future__ import annotations

import pytest
import yaml

from src.agent.actions.models import (
    ActionStatus,
    AgentAction,
    AgentActionType,
    AgentApprovalRequest,
    ApprovalStatus,
)
from src.agent.actions.service import AgentActionService, AgentApprovalService
from src.agent.configuration.configuration_service import ConfigurationService
from src.events.message_event_bus import MessageEventBus
from src.vcs.application.service import VCSService
from tests.unit.api_server.helpers import make_db_manager

SAMPLE_CONFIG = """
assets:
  - name: "Bitcoin (Crypto.com)"
    base_ticker_symbol: "BTC"
    quote_ticker_symbol: "USD"
    exchange: "CRYPTO_DOT_COM"
    min_quantity: 0.00005
    quote_decimals: 2
    quantity_decimals: 5
    candles_timeframe: "MIN1"
    schedule: 1
    consensus:
      buy: 1.3
      sell: 0.5
dynamic_quantity: "max(min_qty, eq * 0.1)"
"""


@pytest.fixture
def db_manager(tmp_path):
    db_mgr = make_db_manager(str(tmp_path / "app.db"))
    VCSService(db_mgr).seed_if_empty(yaml.safe_load(SAMPLE_CONFIG), author="test", message="seed")
    return db_mgr


@pytest.fixture
def vcs(db_manager):
    return VCSService(db_manager)


@pytest.fixture
def config_service(vcs):
    return ConfigurationService(vcs=vcs)


@pytest.fixture
def action_service():
    return AgentActionService(event_bus=MessageEventBus())


@pytest.fixture
def approval_service(vcs, config_service, action_service):
    return AgentApprovalService(
        vcs=vcs,
        configuration_service=config_service,
        action_service=action_service,
        event_bus=MessageEventBus(),
    )


def test_request_and_reject_approval(approval_service, action_service, vcs):
    head_commit = vcs.head("HEAD").hash
    action = action_service.create_action(
        AgentAction(type=AgentActionType.APPLY_CONFIGURATION, title="Update Consensus", description="")
    )

    req = AgentApprovalRequest(
        agent_action_id=action.id,
        action_type="APPLY_CONFIGURATION",
        title="Update Consensus",
        description="Change buy consensus to 1.1",
        base_commit=head_commit,
        proposed_change={
            "changes": [
                {
                    "path": "assets.BTC_USD.consensus.buy",
                    "old_value": 1.3,
                    "new_value": 1.1,
                    "reason": "Optimize frequency",
                }
            ]
        },
    )
    created_req = approval_service.request_approval(req)
    assert created_req.status == ApprovalStatus.PENDING
    assert action_service.get_action(action.id).status == ActionStatus.WAITING_FOR_USER

    # Reject
    resolved, commit_hash, warnings = approval_service.decide_approval(created_req.id, "reject")
    assert resolved.status == ApprovalStatus.REJECTED
    assert commit_hash is None
    assert action_service.get_action(action.id).status == ActionStatus.REJECTED


def test_approve_and_commit_success(approval_service, action_service, vcs):
    head_commit = vcs.head("HEAD").hash
    action = action_service.create_action(
        AgentAction(type=AgentActionType.APPLY_CONFIGURATION, title="Update Consensus", description="")
    )

    req = AgentApprovalRequest(
        agent_action_id=action.id,
        action_type="APPLY_CONFIGURATION",
        title="Update Consensus",
        description="Change buy consensus to 1.1",
        base_commit=head_commit,
        proposed_change={
            "changes": [
                {
                    "path": "assets.BTC_USD.consensus.buy",
                    "old_value": 1.3,
                    "new_value": 1.1,
                    "reason": "Optimize frequency",
                }
            ]
        },
    )
    created_req = approval_service.request_approval(req)

    resolved, commit_hash, warnings = approval_service.decide_approval(created_req.id, "approve")
    assert resolved.status == ApprovalStatus.APPROVED
    assert commit_hash is not None
    assert vcs.head("HEAD").hash == commit_hash
    assert vcs.checkout("HEAD")["assets"][0]["consensus"]["buy"] == 1.1
    assert action_service.get_action(action.id).status == ActionStatus.COMPLETED


def test_approve_conflict_when_base_commit_diverged(approval_service, action_service, vcs):
    outdated_commit = "deadbeef1234567890abcdef1234567890abcdef"
    action = action_service.create_action(
        AgentAction(type=AgentActionType.APPLY_CONFIGURATION, title="Outdated Proposal", description="")
    )

    req = AgentApprovalRequest(
        agent_action_id=action.id,
        action_type="APPLY_CONFIGURATION",
        title="Outdated Proposal",
        description="Proposal based on stale HEAD",
        base_commit=outdated_commit,
        proposed_change={
            "changes": [
                {
                    "path": "assets.BTC_USD.consensus.buy",
                    "old_value": 1.3,
                    "new_value": 1.1,
                    "reason": "test",
                }
            ]
        },
    )
    created_req = approval_service.request_approval(req)

    with pytest.raises(ValueError, match="out of date"):
        approval_service.decide_approval(created_req.id, "approve")

    assert approval_service.get_approval(created_req.id).status == ApprovalStatus.EXPIRED
    assert action_service.get_action(action.id).status == ActionStatus.FAILED
