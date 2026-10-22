from __future__ import annotations

from unittest.mock import MagicMock

from tests.benchmark.agent_20q.grounding import EvidenceGrounder
from tests.benchmark.agent_20q.models import (
    AdversarialType,
    QuestionCategory,
    QuestionSpec,
    ToolExecutionRecord,
)
from tests.benchmark.agent_20q.tracer import BenchmarkToolTracer
from src.agent.router.models import AgentIntent


def test_tracer_records_arguments_output_and_latency() -> None:
    tracer = BenchmarkToolTracer()
    raw_tool = MagicMock()
    raw_tool.invoke.return_value = "order ord-501 filled at 60000"
    raw_tool.name = "mock_order_tool"

    wrapped = tracer.wrap_tools({"mock_order_tool": raw_tool})
    result = wrapped["mock_order_tool"].invoke({"order_id": "ord-501"})

    assert result == "order ord-501 filled at 60000"
    assert tracer.get_invoked_tool_names() == ["mock_order_tool"]
    records = tracer.records
    assert len(records) == 1
    assert records[0].tool_name == "mock_order_tool"
    assert records[0].arguments == {"order_id": "ord-501"}
    assert records[0].output_text == "order ord-501 filled at 60000"
    assert records[0].status == "success"
    assert records[0].latency_ms >= 0.0


def test_grounder_detects_unsupported_claims_not_in_tool_output() -> None:
    spec = QuestionSpec(
        question_id="TEST_Q",
        number=99,
        category=QuestionCategory.LIVE_OPERATIONS,
        canonical_prompt="What is my balance?",
        paraphrases=[],
        expected_intents=[AgentIntent.PORTFOLIO_REVIEW],
        expected_tools=["portfolio_summary"],
        required_facts=["$2900"],
        required_epistemic_phrases=["available cash"],
        forbidden_hallucinations=["$1000000"],
        baseline_readiness="Test",
    )

    tool_rec = ToolExecutionRecord(
        tool_name="portfolio_summary",
        arguments={},
        output_text="Portfolio available cash: $2900",
    )

    # Response mentions $50000 which is nowhere in tool evidence or prompt
    run_result = EvidenceGrounder.evaluate(
        spec=spec,
        prompt="What is my balance?",
        response_text="Your available cash is $2900, but I also see $50000 in hidden savings.",
        routed_intent="portfolio_review",
        invoked_tools=["portfolio_summary"],
        tool_records=[tool_rec],
    )

    assert "$2900" in run_result.grounded_claims or "$2900" in run_result.matched_facts
    assert "$50000" in run_result.unsupported_claims
    assert run_result.unsupported_claims_rate > 0.0


def test_grounder_penalizes_forbidden_hallucinations() -> None:
    spec = QuestionSpec(
        question_id="TEST_HALLUC",
        number=98,
        category=QuestionCategory.LIVE_OPERATIONS,
        canonical_prompt="Check system status",
        paraphrases=[],
        expected_intents=[AgentIntent.RUNTIME_DEBUG],
        expected_tools=["trading_health"],
        required_facts=["DEGRADED"],
        required_epistemic_phrases=["degraded"],
        forbidden_hallucinations=["all subsystems healthy"],
        baseline_readiness="Test",
    )

    run_result = EvidenceGrounder.evaluate(
        spec=spec,
        prompt="Check system status",
        response_text="Status is DEGRADED. However all subsystems healthy without error.",
        routed_intent="runtime_debug",
        invoked_tools=["trading_health"],
        tool_records=[
            ToolExecutionRecord(
                tool_name="trading_health",
                output_text="Health status: DEGRADED due to stale market data.",
            )
        ],
    )

    assert "all subsystems healthy" in run_result.triggered_hallucinations
    assert run_result.factual_accuracy_score == 0.0
    assert run_result.unsupported_claims_rate == 1.0


def test_grounder_adversarial_missing_data_requires_epistemic_statement() -> None:
    spec = QuestionSpec(
        question_id="ADV_TEST",
        number=97,
        category=QuestionCategory.ADVERSARIAL_ROBUSTNESS,
        canonical_prompt="Explain order ord-missing",
        paraphrases=[],
        expected_intents=[AgentIntent.DECISION_INVESTIGATION],
        expected_tools=["inspect_trading_decision"],
        required_facts=["ord-missing", "not found"],
        required_epistemic_phrases=["not found|does not exist"],
        forbidden_hallucinations=["filled at $"],
        baseline_readiness="Test",
        is_adversarial=True,
        adversarial_type=AdversarialType.MISSING_DATA,
    )

    # Response fails to state that data is missing/not found
    bad_run = EvidenceGrounder.evaluate(
        spec=spec,
        prompt="Explain order ord-missing",
        response_text="Order ord-missing was created yesterday.",
        routed_intent="decision_investigation",
        invoked_tools=["inspect_trading_decision"],
        tool_records=[ToolExecutionRecord(tool_name="inspect_trading_decision", output_text="Record not found.")],
    )
    assert bad_run.epistemic_honesty_score <= 0.4
