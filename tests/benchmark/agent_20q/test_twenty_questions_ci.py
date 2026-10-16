from __future__ import annotations
# pylint: disable=redefined-outer-name

import pytest

from tests.benchmark.agent_20q.evaluator import TwentyQuestionsEvaluator
from tests.benchmark.agent_20q.models import QuestionSpec
from tests.benchmark.agent_20q.scenarios import (
    TWENTY_QUESTIONS,
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
    TWENTY_QUESTIONS,
    ids=[q.question_id for q in TWENTY_QUESTIONS],
)
def test_each_acceptance_question_passes_grounded_contract_and_paraphrases(
    evaluator: TwentyQuestionsEvaluator,
    question_spec: QuestionSpec,
) -> None:
    score = evaluator.evaluate_question(question_spec, include_paraphrases=True)
    assert score.passed, (
        f"{question_spec.question_id} failed: total={score.weighted_total_score}, "
        f"route={score.route_and_tool_score}, facts={score.fact_recall_score}, "
        f"epistemic={score.epistemic_guardrail_score}, consistency={score.consistency_score}, "
        f"missing_facts={[r.missing_facts for r in score.runs]}, "
        f"missing_epistemic={[r.missing_epistemic for r in score.runs]}, "
        f"hallucinations={[r.triggered_hallucinations for r in score.runs]}"
    )


def test_anti_hallucination_gate_fails_when_forbidden_claim_present() -> None:
    spec = TWENTY_QUESTIONS[0]
    hallucinated_run = TwentyQuestionsEvaluator.grade_response(
        spec=spec,
        prompt=spec.canonical_prompt,
        response_text="All subsystems healthy and fully healthy and trading all assets.",
        routed_intent=spec.expected_intents[0].value,
        invoked_tools=spec.expected_tools,
    )
    score = TwentyQuestionsEvaluator.score_question(spec, [hallucinated_run])
    assert score.passed is False and len(hallucinated_run.triggered_hallucinations) > 0


def test_q03_and_q19_schedule_tick_tracer_links_events_end_to_end(
    seeded_env: SeededBenchmarkEnvironment,
) -> None:
    tool_output = seeded_env.tools["inspect_schedule_tick_trace"].invoke(
        {"ticker_symbol": "BTC_USD", "limit": 5}
    )
    assert "tick-1901" in tool_output and "QUORUM_NOT_MET" in tool_output


def test_q06_and_q18_decision_inspector_exposes_strategy_rejections_and_guard_limits(
    seeded_env: SeededBenchmarkEnvironment,
) -> None:
    out_601 = seeded_env.tools["inspect_trading_decision"].invoke(
        {"action": "get_by_id", "decision_id": "dec-601"}
    )
    out_1801 = seeded_env.tools["inspect_trading_decision"].invoke(
        {"action": "get_by_id", "decision_id": "dec-1801"}
    )
    assert (
        "BollingerStrategy: QUORUM_NOT_MET" in out_601
        and "MaxAssetConcentrationGuard [REJECTED]" in out_1801
    )


def test_q10_and_q11_trade_attribution_reconciles_proportional_pnl_and_regimes(
    seeded_env: SeededBenchmarkEnvironment,
) -> None:
    strat_out = seeded_env.tools["get_trade_attribution"].invoke(
        {"dimension": "strategy", "days": 30}
    )
    regime_out = seeded_env.tools["get_trade_attribution"].invoke(
        {"dimension": "strategy_by_regime", "days": 30}
    )
    assert (
        "Reconciled Portfolio Realized Net PnL: +$120.00" in strat_out
        and "[LOW SAMPLE SIZE]" in regime_out
    )


def test_q12_backtest_drift_tool_reports_window_fees_and_merged_partial_fills(
    seeded_env: SeededBenchmarkEnvironment,
) -> None:
    drift_out = seeded_env.tools["detect_backtest_drift"].invoke({"ticker_symbol": "BTC_USD"})
    assert "Partial fill legs merged: 1" in drift_out and "Fee drift: $-1.20" in drift_out


def test_q14_walk_forward_tool_compares_candidates_and_flags_overfitting(
    seeded_env: SeededBenchmarkEnvironment,
) -> None:
    wf_out = seeded_env.tools["walk_forward"].invoke(
        {"action": "compare_candidates", "ticker_symbol": "BTC_USD"}
    )
    assert "cand_robust_multi" in wf_out and "OVERFIT" in wf_out


def test_q15_and_q16_experiment_inspector_reports_provenance_and_justification(
    seeded_env: SeededBenchmarkEnvironment,
) -> None:
    prov_out = seeded_env.tools["inspect_experiment"].invoke(
        {"action": "get", "experiment_id": "exp_901"}
    )
    just_out = seeded_env.tools["inspect_experiment"].invoke(
        {"action": "evaluate_justification", "ticker_symbol": "CRO_USD"}
    )
    assert "BACKTEST_DRIFT_DETECTED" in prov_out and "DO NOT TRIGGER EXPERIMENT" in just_out


def test_q17_portfolio_summary_reports_valuation_timestamp_reserved_orders_and_missing_prices(
    seeded_env: SeededBenchmarkEnvironment,
) -> None:
    summary_out = seeded_env.tools["portfolio_summary"].invoke({"quote_currency": "USD"})
    assert (
        "Valuation Timestamp: 2026-10-16T09:00:00Z" in summary_out
        and "Unavailable Price Data: SOL_USD" in summary_out
    )


def test_q20_retention_governance_distinguishes_dry_run_from_executed_deletion(
    seeded_env: SeededBenchmarkEnvironment,
) -> None:
    ret_out = seeded_env.tools["inspect_retention_governance"].invoke({"action": "summary"})
    assert "ret_run_01" in ret_out and "DEPENDENCY_REFERENCED" in ret_out


def test_full_20q_suite_report_generates_markdown_and_passes_100_percent(
    evaluator: TwentyQuestionsEvaluator,
) -> None:
    report = evaluator.run_suite(include_paraphrases=True)
    md = report.to_markdown()
    assert report.passed_questions == 20 and "## Category Breakdown" in md
