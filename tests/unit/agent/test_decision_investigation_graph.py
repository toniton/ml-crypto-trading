import asyncio
from unittest.mock import MagicMock

from src.agent.actions.models import AgentActionType, AgentApprovalRequest, ApprovalStatus
from src.agent.actions.service import AgentActionService, AgentApprovalService
from src.agent.decision_investigation.graph import DecisionInvestigationGraph
from src.agent.decision_investigation.models import DecisionExplanation
from src.agent.gateway import AgentGateway
from src.agent.router.models import AgentIntent, AgentReferences, AgentRoute
from tests.unit.agent.fakes import FakeLlmAdapter


class TestDecisionInvestigationGraph:
    def test_reconstructs_evidence_and_synthesizes_causal_story(self):
        llm = FakeLlmAdapter([
            DecisionExplanation(
                summary="Reduced exposure and tightened consensus buy threshold due to quote balance constraints.",
                causal_story="1. Trigger: Starvation watchdog detected 0 fills.\n2. Action: Increased buy threshold.",
                key_factors=["Order starvation", "Quote reserve balance"],
            )
        ])

        action_service = AgentActionService()
        approval_service = AgentApprovalService(
            vcs=MagicMock(),
            configuration_service=MagicMock(),
            action_service=action_service,
        )

        approval_req = AgentApprovalRequest(
            id="appr-123",
            agent_action_id="act-123",
            action_type=AgentActionType.CREATE_PROPOSAL,
            title="Update CRO_USD parameters",
            description="Starvation detected on CRO_USD",
            base_commit="235f666a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e",
            asset="CRO_USD",
            status=ApprovalStatus.PENDING,
            proposed_change={
                "changes": [
                    {
                        "path": "assets.CRO_USD.consensus.buy",
                        "old_value": 0.5,
                        "new_value": 1.0,
                        "reason": "Tighten threshold after repeated starvation",
                    }
                ],
                "risks": ["May reduce trade frequency"],
                "expected_effect": "Avoid unfillable small orders",
            },
        )
        approval_service._approvals["appr-123"] = approval_req

        graph = DecisionInvestigationGraph(
            llm=llm,
            approval_service=approval_service,
        ).build()

        state = graph.invoke({
            "user_prompt": "Why are you proposing these changes for CRO_USD (Base: 235f666)?",
            "request": AgentRoute(
                intent=AgentIntent.DECISION_INVESTIGATION,
                references=AgentReferences(asset="CRO_USD", commit_hash="235f666"),
            ),
        })

        assert state["evidence"] is not None
        assert state["evidence"].asset == "CRO_USD"
        assert state["evidence"].base_commit == "235f666a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e"
        assert len(state["evidence"].configuration_changes) == 1
        assert state["evidence"].configuration_changes[0].new_value == 1.0

        assert state["explanation"] is not None
        assert "Starvation watchdog" in state["explanation"].causal_story

        assert state["presentation"] is not None
        assert len(state["presentation"].blocks) == 1
        assert "Proposed Parameter Changes" in state["presentation"].blocks[0]["content"]

    def test_gateway_stream_routes_to_decision_investigation(self):
        llm = FakeLlmAdapter([
            AgentRoute(
                intent=AgentIntent.DECISION_INVESTIGATION,
                references=AgentReferences(asset="CRO_USD", commit_hash="235f666"),
            ),
            DecisionExplanation(
                summary="Explanation of proposal for CRO_USD",
                causal_story="Reconstructed causal chain",
                key_factors=["Starvation"],
            ),
        ])

        vcs_mock = MagicMock()
        action_service = AgentActionService()
        approval_service = AgentApprovalService(
            vcs=vcs_mock,
            configuration_service=MagicMock(),
            action_service=action_service,
        )

        approval_req = AgentApprovalRequest(
            id="appr-cro",
            agent_action_id="act-cro",
            action_type=AgentActionType.CREATE_PROPOSAL,
            title="CRO proposal",
            description="Autonomous adjustment",
            base_commit="235f666",
            asset="CRO_USD",
            status=ApprovalStatus.PENDING,
            proposed_change={
                "changes": [{"path": "assets.CRO_USD.consensus.buy", "old_value": 0.5, "new_value": 1.0}],
            },
        )
        approval_service._approvals["appr-cro"] = approval_req

        gateway = AgentGateway(
            llm=llm,
            vcs=vcs_mock,
            approval_service=approval_service,
        )

        async def collect():
            return [ev async for ev in gateway.stream("Why are you proposing these changes for CRO_USD (Base: 235f666)?")]

        events = asyncio.run(collect())

        agents = [ev.agent for ev in events if ev.agent]
        assert "decision_investigation" in agents
        assert "configuration" not in agents  # Proves it did not run configuration graph!

        done_event = next(ev for ev in events if ev.type == "done")
        assert done_event.payload.get("kind") == "decision_investigation"

    def test_falls_back_to_timeline_projector_when_approval_service_empty(self):
        llm = FakeLlmAdapter([
            DecisionExplanation(
                summary="Fallback explanation reconstructed from timeline.",
                causal_story="1. Trigger: Anomaly detected.\n2. Action: Proposed change.",
                key_factors=["Anomaly"],
            )
        ])

        timeline_mock = MagicMock()
        timeline_mock.list_items.return_value = [
            {
                "id": "tl-appr-1",
                "title": "Anomaly adjustment",
                "summary": "Detected anomaly on CRO_USD",
                "metadata": {
                    "approval_id": "appr-timeline-1",
                    "asset": "CRO_USD",
                    "base_commit": "235f666a1b2c3d4e",
                    "status": "PENDING",
                    "proposed_change": {
                        "changes": [
                            {
                                "path": "assets.CRO_USD.consensus.buy",
                                "old_value": 0.5,
                                "new_value": 1.0,
                            }
                        ]
                    },
                },
            }
        ]

        graph = DecisionInvestigationGraph(
            llm=llm,
            timeline_projector=timeline_mock,
        ).build()

        state = graph.invoke({
            "user_prompt": "Why are you proposing these changes for CRO_USD (Base: 235f666)?",
            "request": AgentRoute(
                intent=AgentIntent.DECISION_INVESTIGATION,
                references=AgentReferences(asset="CRO_USD", commit_hash="235f666"),
            ),
        })

        assert state["evidence"] is not None
        assert state["evidence"].asset == "CRO_USD"
        assert state["evidence"].base_commit == "235f666a1b2c3d4e"
        assert len(state["evidence"].configuration_changes) == 1
        assert state["evidence"].configuration_changes[0].new_value == 1.0

    def test_detects_consistency_warning_when_base_config_mismatches_proposal(self):
        llm = FakeLlmAdapter([
            DecisionExplanation(
                summary="Mismatch detected between proposal baseline and VCS base commit.",
                causal_story="1. Baseline was 0.3 but proposal claimed 0.5.",
                key_factors=["State drift"],
            )
        ])

        vcs_mock = MagicMock()
        vcs_mock.resolve_commit_hash.return_value = "235f666a1b2c3d4e"
        commit_mock = MagicMock()
        commit_mock.message = "Autonomous adjustment commit"
        commit_mock.author = "agent"
        vcs_mock.head.return_value = commit_mock
        vcs_mock.checkout.return_value = {
            "assets": {
                "CRO_USD": {
                    "consensus": {
                        "buy": 0.3  # Actual base has 0.3, while proposal claims old_value is 0.5!
                    }
                }
            }
        }

        approval_service = AgentApprovalService(
            vcs=vcs_mock,
            configuration_service=MagicMock(),
            action_service=AgentActionService(),
        )

        approval_req = AgentApprovalRequest(
            id="appr-drift",
            agent_action_id="act-drift",
            action_type=AgentActionType.CREATE_PROPOSAL,
            title="Update CRO_USD",
            description="Adjust buy consensus",
            base_commit="235f666a1b2c3d4e",
            asset="CRO_USD",
            status=ApprovalStatus.PENDING,
            proposed_change={
                "changes": [
                    {
                        "path": "assets.CRO_USD.consensus.buy",
                        "old_value": 0.5,
                        "new_value": 1.0,
                    }
                ]
            },
        )
        approval_service._approvals["appr-drift"] = approval_req

        graph = DecisionInvestigationGraph(
            llm=llm,
            vcs=vcs_mock,
            approval_service=approval_service,
        ).build()

        state = graph.invoke({
            "user_prompt": "Why are you proposing these changes for CRO_USD (Base: 235f666)?",
            "request": AgentRoute(
                intent=AgentIntent.DECISION_INVESTIGATION,
                references=AgentReferences(asset="CRO_USD", commit_hash="235f666"),
            ),
        })

        assert state["evidence"] is not None
        assert len(state["evidence"].consistency_warnings) == 1
        assert "Value mismatch for 'assets.CRO_USD.consensus.buy'" in state["evidence"].consistency_warnings[0]
        assert state["evidence"].commit_message == "Autonomous adjustment commit"
        assert state["evidence"].commit_author == "agent"

    def test_investigates_historical_commit_without_approval(self):
        llm = FakeLlmAdapter([
            DecisionExplanation(
                summary="Explains historical commit 235f666 based on commit message and VCS history.",
                causal_story="Commit made by developer to adjust parameters.",
                key_factors=["Manual change"],
            )
        ])

        vcs_mock = MagicMock()
        vcs_mock.resolve_commit_hash.return_value = "235f666a1b2c3d4e"
        commit_mock = MagicMock()
        commit_mock.message = "Fix authoritative exchange available balance propagation"
        commit_mock.author = "toniton"
        vcs_mock.head.return_value = commit_mock
        vcs_mock.checkout.return_value = {"assets": {"CRO_USD": {}}}

        graph = DecisionInvestigationGraph(
            llm=llm,
            vcs=vcs_mock,
        ).build()

        state = graph.invoke({
            "user_prompt": "Why was commit 235f666 created?",
            "request": AgentRoute(
                intent=AgentIntent.DECISION_INVESTIGATION,
                references=AgentReferences(commit_hash="235f666"),
            ),
        })

        assert state["evidence"] is not None
        assert state["evidence"].resolved_commit_hash == "235f666a1b2c3d4e"
        assert state["evidence"].commit_message == "Fix authoritative exchange available balance propagation"
        assert state["evidence"].commit_author == "toniton"
        assert state["presentation"] is not None
        assert "Commit Message" in state["presentation"].blocks[0]["content"]



