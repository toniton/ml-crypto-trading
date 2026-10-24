from __future__ import annotations
# pylint: disable=redefined-outer-name

import pytest

from tests.benchmark.agent_20q.adversarial_scenarios import ADVERSARIAL_QUESTIONS
from tests.benchmark.agent_20q.evaluator import TwentyQuestionsEvaluator
from tests.benchmark.agent_20q.models import QuestionSpec
from tests.benchmark.agent_20q.scenarios import (
    SeededBenchmarkEnvironment,
    build_seeded_environment,
)


@pytest.fixture(scope="module")
def seeded_env() -> SeededBenchmarkEnvironment:
    return build_seeded_environment()


@pytest.fixture(scope="module")
def evaluator(seeded_env: SeededBenchmarkEnvironment) -> TwentyQuestionsEvaluator:
    return TwentyQuestionsEvaluator(env=seeded_env)


@pytest.mark.parametrize(
    "question_spec",
    ADVERSARIAL_QUESTIONS,
    ids=[q.question_id for q in ADVERSARIAL_QUESTIONS],
)
def test_adversarial_scenarios_pass_epistemic_and_grounding_checks(
    evaluator: TwentyQuestionsEvaluator,
    question_spec: QuestionSpec,
) -> None:
    score = evaluator.evaluate_question(question_spec, include_paraphrases=True)
    assert score.passed, (
        f"{question_spec.question_id} failed: total={score.weighted_total_score}, "
        f"tool_selection={score.tool_selection_score}, fact_accuracy={score.factual_accuracy_score}, "
        f"epistemic={score.epistemic_honesty_score}, unsupp_rate={score.unsupported_claims_rate}, "
        f"missing_facts={[r.missing_facts for r in score.runs]}, "
        f"missing_epistemic={[r.missing_epistemic for r in score.runs]}, "
        f"unsupported_claims={[r.unsupported_claims for r in score.runs]}, "
        f"hallucinations={[r.triggered_hallucinations for r in score.runs]}"
    )


def test_adversarial_suite_run_passes_quality_gate(
        evaluator: TwentyQuestionsEvaluator,
) -> None:
    report = evaluator.run_suite(
        questions=ADVERSARIAL_QUESTIONS,
        include_paraphrases=True,
        trials=1,
    )
    assert report.quality_gate_passed, f"Gate failed: {report.quality_gate_reasons}"
    assert report.passed_questions == len(ADVERSARIAL_QUESTIONS)
    assert report.mean_unsupported_claims_rate == 0.0
