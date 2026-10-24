from __future__ import annotations
# pylint: disable=redefined-outer-name

import pytest

from tests.benchmark.agent_50q.evaluator import FiftyQuestionsEvaluator
from tests.benchmark.agent_50q.models import (
    CriticalGateId,
    FiftyQuestionCategory,
)
from tests.benchmark.agent_50q.scenarios import FIFTY_QUESTIONS


def test_suite_contains_exactly_fifty_questions() -> None:
    assert len(FIFTY_QUESTIONS) == 50
    ids = [q.question_id for q in FIFTY_QUESTIONS]
    assert len(set(ids)) == 50
    numbers = [q.number for q in FIFTY_QUESTIONS]
    assert numbers == list(range(1, 51))


def test_all_ten_categories_have_exactly_five_questions() -> None:
    category_counts: dict[FiftyQuestionCategory, int] = {}
    for q in FIFTY_QUESTIONS:
        category_counts[q.category] = category_counts.get(q.category, 0) + 1

    assert len(category_counts) == 10
    for cat, count in category_counts.items():
        assert count == 5, f"{cat.value} has {count} questions instead of 5"


def test_critical_regression_gates_are_defined() -> None:
    gate_questions = [q for q in FIFTY_QUESTIONS if q.critical_gate is not None]
    assert len(gate_questions) >= 10
    gate_ids = {q.critical_gate for q in gate_questions}
    assert CriticalGateId.GATE_Q11 in gate_ids
    assert CriticalGateId.GATE_Q06_Q10 in gate_ids
    assert CriticalGateId.GATE_Q13_Q15 in gate_ids
    assert CriticalGateId.GATE_Q23_Q30 in gate_ids
    assert CriticalGateId.GATE_Q41_Q44 in gate_ids
    assert CriticalGateId.GATE_Q50 in gate_ids


@pytest.fixture(scope="module")
def evaluator() -> FiftyQuestionsEvaluator:
    return FiftyQuestionsEvaluator(mode="deterministic")


@pytest.mark.parametrize(
    "question_id",
    ["Q01", "Q06", "Q07", "Q08", "Q10", "Q11", "Q23", "Q30", "Q50"],
)
def test_critical_gates_pass_grounded_validation(
    evaluator: FiftyQuestionsEvaluator,
    question_id: str,
) -> None:
    spec = next(q for q in FIFTY_QUESTIONS if q.question_id == question_id)
    score = evaluator.evaluate_question(spec)
    assert score.critical_gate_passed, (
        f"{question_id} critical gate failed: {score.gate_evaluation.reason if score.gate_evaluation else 'unknown'}"
    )
    assert score.rubric.weighted_total >= 0.70, (
        f"{question_id} rubric total {score.rubric.weighted_total} below 0.70"
    )
