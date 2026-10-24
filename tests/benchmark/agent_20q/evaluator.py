from __future__ import annotations
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments,too-many-statements

from datetime import datetime, timezone
import statistics
import time
from typing import Any, List, Optional

from src.agent.gateway import AgentGateway
from src.core.interfaces.llm_adapter import LlmAdapter
from tests.benchmark.agent_20q.grounding import EvidenceGrounder
from tests.benchmark.agent_20q.models import (
    BenchmarkProvenance,
    BenchmarkSuiteReport,
    PromptRunResult,
    QuestionScore,
    QuestionSpec,
    ToolExecutionRecord,
)
from tests.benchmark.agent_20q.scenarios import (
    TWENTY_QUESTIONS,
    SeededBenchmarkEnvironment,
    build_seeded_environment,
)
from tests.benchmark.agent_20q.scripted_llm import BenchmarkScriptedLlmAdapter
from tests.benchmark.agent_20q.tracer import BenchmarkToolTracer


class TwentyQuestionsEvaluator:
    def __init__(
            self,
            env: Optional[SeededBenchmarkEnvironment] = None,
            llm_adapter: Optional[LlmAdapter] = None,
            mode: str = "deterministic",
            model_id: str = "scripted-deterministic-v1",
    ) -> None:
        self.env = env or build_seeded_environment()
        self.tracer = BenchmarkToolTracer()
        self.env.tools = self.tracer.wrap_tools(self.env.tools)

        self.mode = mode
        self.model_id = model_id
        self.llm: LlmAdapter = llm_adapter or BenchmarkScriptedLlmAdapter(self.env)
        if not isinstance(self.llm, BenchmarkScriptedLlmAdapter):
            self.llm.bind_tools(self.env.tools)
        self.gateway = AgentGateway(
            llm=self.llm,
            vcs=self.env.vcs,
            approval_service=self.env.approval_service,
            timeline_projector=self.env.timeline_projector,
            health_monitor=self.env.health_monitor,
        )

    def run_suite(
            self,
            questions: Optional[list[QuestionSpec]] = None,
            include_paraphrases: bool = True,
            trials: int = 1,
            provenance: Optional[BenchmarkProvenance] = None,
            fail_under_score: float = 0.85,
            max_unsupported_rate: float = 0.0,
            delay_seconds: float = 0.0,
    ) -> BenchmarkSuiteReport:
        specs = questions or TWENTY_QUESTIONS
        scores: list[QuestionScore] = []
        for idx, spec in enumerate(specs, start=1):
            if self.mode == "live":
                print(f"[{idx}/{len(specs)}] Evaluating {spec.question_id}: {spec.canonical_prompt}...", flush=True)
            score = self.evaluate_question(
                spec,
                include_paraphrases=include_paraphrases,
                trials=trials,
                delay_seconds=delay_seconds,
            )
            scores.append(score)
            if self.mode == "live":
                status = "PASS" if score.passed else "FAIL"
                print(
                    f"  -> {status} (score={score.weighted_total_score * 100:.1f}%, "
                    f"latency={score.avg_latency_ms:.0f}ms)",
                    flush=True,
                )
        total_q = len(scores)
        passed_q = sum(1 for s in scores if s.passed)
        pass_rate = (passed_q / total_q * 100.0) if total_q else 0.0
        mean_score = sum(s.weighted_total_score for s in scores) / total_q if total_q else 0.0
        mean_route = sum(s.route_and_tool_score for s in scores) / total_q if total_q else 0.0
        mean_fact = sum(s.fact_recall_score for s in scores) / total_q if total_q else 0.0
        mean_epist = sum(s.epistemic_guardrail_score for s in scores) / total_q if total_q else 0.0
        mean_cons = sum(s.consistency_score for s in scores) / total_q if total_q else 0.0

        mean_tool_sel = sum(s.tool_selection_score for s in scores) / total_q if total_q else 0.0
        mean_fact_acc = sum(s.factual_accuracy_score for s in scores) / total_q if total_q else 0.0
        mean_unsupp = sum(s.unsupported_claims_rate for s in scores) / total_q if total_q else 0.0
        mean_epist_hon = sum(s.epistemic_honesty_score for s in scores) / total_q if total_q else 0.0

        all_latencies = [r.latency_ms for s in scores for r in s.runs] or [0.0]
        sorted_lat = sorted(all_latencies)
        p50 = statistics.median(sorted_lat)
        p95_idx = min(len(sorted_lat) - 1, int(len(sorted_lat) * 0.95))
        p95 = sorted_lat[p95_idx]

        gate_reasons: list[str] = []
        if passed_q < total_q:
            failed_ids = [s.question_id for s in scores if not s.passed]
            gate_reasons.append(f"Failed questions ({len(failed_ids)}): {', '.join(failed_ids)}")
        if mean_score < fail_under_score:
            gate_reasons.append(
                f"Mean score {mean_score:.3f} below quality threshold {fail_under_score:.3f}"
            )
        if mean_unsupp > max_unsupported_rate:
            gate_reasons.append(
                f"Mean unsupported claims rate {mean_unsupp:.3f} exceeded max allowed {max_unsupported_rate:.3f}"
            )

        gate_passed = len(gate_reasons) == 0

        return BenchmarkSuiteReport(
            model_id=self.model_id,
            mode=self.mode,
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_questions=total_q,
            passed_questions=passed_q,
            pass_rate_pct=round(pass_rate, 2),
            mean_score=round(mean_score, 4),
            mean_route_tool_score=round(mean_route, 4),
            mean_fact_recall=round(mean_fact, 4),
            mean_epistemic_score=round(mean_epist, 4),
            mean_consistency_score=round(mean_cons, 4),
            p50_latency_ms=round(p50, 2),
            p95_latency_ms=round(p95, 2),
            question_scores=scores,
            provenance=provenance,
            num_trials=trials,
            mean_tool_selection_score=round(mean_tool_sel, 4),
            mean_factual_accuracy=round(mean_fact_acc, 4),
            mean_unsupported_claims_rate=round(mean_unsupp, 4),
            mean_epistemic_honesty=round(mean_epist_hon, 4),
            quality_gate_passed=gate_passed,
            quality_gate_reasons=gate_reasons,
        )

    def evaluate_question(
            self,
            spec: QuestionSpec,
            include_paraphrases: bool = True,
            trials: int = 1,
            delay_seconds: float = 0.0,
    ) -> QuestionScore:
        prompts = spec.all_prompts if include_paraphrases else [spec.canonical_prompt]
        prompt_results: list[PromptRunResult] = []
        for _ in range(max(1, trials)):
            for prompt in prompts:
                prompt_results.append(self.evaluate_prompt(spec, prompt))
                if delay_seconds > 0.0:
                    time.sleep(delay_seconds)
        return self.score_question(spec, prompt_results)

    def evaluate_prompt(self, spec: QuestionSpec, prompt: str) -> PromptRunResult:
        self.tracer.clear()
        if isinstance(self.llm, BenchmarkScriptedLlmAdapter):
            self.llm.reset_turn_tracking()

        start_ns = time.perf_counter_ns()
        try:
            result = self.gateway.handle(prompt, history=[])
            response_text = self._extract_presentation_text(result)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            result = None
            response_text = f"Model execution error: {exc}"
        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0

        invoked_tools = self.tracer.get_invoked_tool_names()
        if not invoked_tools and isinstance(self.llm, BenchmarkScriptedLlmAdapter):
            invoked_tools = list(self.llm.invoked_tools)

        routed_intent = ""
        if getattr(self.gateway, "last_route", None) is not None:
            routed_intent = self.gateway.last_route.intent.value
        elif isinstance(self.llm, BenchmarkScriptedLlmAdapter) and self.llm.routed_intent:
            routed_intent = self.llm.routed_intent
        else:
            routed_intent = getattr(result, "kind", "")

        return self.grade_response(
            spec=spec,
            prompt=prompt,
            response_text=response_text,
            routed_intent=routed_intent,
            invoked_tools=invoked_tools,
            tool_records=list(self.tracer.records),
            latency_ms=elapsed_ms,
        )

    @staticmethod
    def grade_response(
            spec: QuestionSpec,
            prompt: str,
            response_text: str,
            routed_intent: str,
            invoked_tools: list[str],
            tool_records: Optional[List[ToolExecutionRecord]] = None,
            latency_ms: float = 0.0,
    ) -> PromptRunResult:
        return EvidenceGrounder.evaluate(
            spec=spec,
            prompt=prompt,
            response_text=response_text,
            routed_intent=routed_intent,
            invoked_tools=invoked_tools,
            tool_records=tool_records or [],
            latency_ms=latency_ms,
        )

    @staticmethod
    def score_question(
            spec: QuestionSpec,
            prompt_results: list[PromptRunResult],
    ) -> QuestionScore:
        if not prompt_results:
            raise ValueError(f"No prompt results to score for {spec.question_id}")

        allowed_intents = {i.value for i in spec.expected_intents}
        route_scores: list[float] = []
        fact_scores: list[float] = []
        epistemic_scores: list[float] = []
        tool_sel_scores: list[float] = []
        fact_acc_scores: list[float] = []
        unsupp_rates: list[float] = []
        epist_hon_scores: list[float] = []
        run_composite_scores: list[float] = []
        hallucination_detected = False

        for run in prompt_results:
            if run.triggered_hallucinations or run.contradicted_claims:
                hallucination_detected = True

            intent_ok = 1.0 if not allowed_intents or run.routed_intent in allowed_intents else 0.0
            if spec.expected_tools:
                matched_tools = sum(1 for t in spec.expected_tools if t in run.invoked_tools)
                tool_ok = matched_tools / len(spec.expected_tools)
            else:
                tool_ok = 1.0
            route_scores.append((intent_ok + tool_ok) / 2.0)

            total_facts = len(spec.required_facts)
            fact_scores.append(
                len(run.matched_facts) / total_facts if total_facts > 0 else 1.0
            )

            total_epistemic = len(spec.required_epistemic_phrases)
            epistemic_scores.append(
                len(run.matched_epistemic) / total_epistemic if total_epistemic > 0 else 1.0
            )

            tool_sel_scores.append(run.tool_selection_score)
            fact_acc_scores.append(run.factual_accuracy_score)
            unsupp_rates.append(run.unsupported_claims_rate)
            epist_hon_scores.append(run.epistemic_honesty_score)

            run_comp = (
                0.20 * run.tool_selection_score
                + 0.40 * run.factual_accuracy_score
                + 0.25 * run.epistemic_honesty_score
                + 0.15 * (1.0 - run.unsupported_claims_rate)
            )
            run_composite_scores.append(run_comp)

        avg_route = sum(route_scores) / len(route_scores)
        avg_fact = sum(fact_scores) / len(fact_scores)
        avg_epistemic = sum(epistemic_scores) / len(epistemic_scores)
        avg_tool_sel = sum(tool_sel_scores) / len(tool_sel_scores)
        avg_fact_acc = sum(fact_acc_scores) / len(fact_acc_scores)
        avg_unsupp = sum(unsupp_rates) / len(unsupp_rates)
        avg_epist_hon = sum(epist_hon_scores) / len(epist_hon_scores)

        # Consistency across prompt runs / trials
        all_runs_complete = all(
            not r.missing_facts
            and not r.missing_epistemic
            and not r.triggered_hallucinations
            and (not allowed_intents or r.routed_intent in allowed_intents)
            for r in prompt_results
        )
        consistency = 1.0 if all_runs_complete else min(avg_fact, avg_epistemic)

        # Cross-trial variance (standard deviation)
        trial_variance = statistics.stdev(run_composite_scores) if len(run_composite_scores) > 1 else 0.0

        if hallucination_detected or avg_unsupp > 0.0:
            avg_fact = 0.0
            avg_fact_acc = 0.0
            avg_epistemic = 0.0
            consistency = 0.0
            weighted_total = 0.0
            passed = False
        else:
            weighted_total = (
                    0.20 * avg_tool_sel
                    + 0.40 * avg_fact_acc
                    + 0.25 * avg_epist_hon
                    + 0.15 * consistency
            )
            passed = (
                    weighted_total >= 0.85
                    and avg_fact >= 0.80
                    and avg_epistemic >= 0.80
                    and consistency >= 0.80
                    and avg_unsupp == 0.0
            )

        avg_latency = sum(r.latency_ms for r in prompt_results) / len(prompt_results)

        return QuestionScore(
            question_id=spec.question_id,
            title=spec.canonical_prompt,
            category=spec.category.value,
            baseline_readiness=spec.baseline_readiness,
            route_and_tool_score=round(avg_route, 4),
            fact_recall_score=round(avg_fact, 4),
            epistemic_guardrail_score=round(avg_epistemic, 4),
            consistency_score=round(consistency, 4),
            weighted_total_score=round(weighted_total, 4),
            passed=passed,
            avg_latency_ms=round(avg_latency, 2),
            runs=prompt_results,
            tool_selection_score=round(avg_tool_sel, 4),
            factual_accuracy_score=round(avg_fact_acc, 4),
            unsupported_claims_rate=round(avg_unsupp, 4),
            epistemic_honesty_score=round(avg_epist_hon, 4),
            trial_variance=round(trial_variance, 4),
        )

    @staticmethod
    def _extract_presentation_text(result: Any) -> str:
        parts: list[str] = []
        presentation = getattr(result, "presentation", None)
        if presentation is not None:
            if hasattr(presentation, "markdown") and callable(presentation.markdown):
                parts.append(str(presentation.markdown()))
            elif hasattr(presentation, "blocks"):
                for block in presentation.blocks:
                    if isinstance(block, dict):
                        parts.append(str(block.get("content", "")))
                    elif hasattr(block, "content"):
                        parts.append(str(block.content))
                    else:
                        parts.append(str(block))

        proposal = getattr(result, "proposal", None)
        if proposal is not None and hasattr(proposal, "summary"):
            parts.append(str(proposal.summary))

        explanation = getattr(result, "explanation", None)
        if explanation is not None:
            if hasattr(explanation, "summary"):
                parts.append(str(explanation.summary))
            if hasattr(explanation, "causal_story"):
                parts.append(str(explanation.causal_story))

        question = getattr(result, "question", None)
        if question:
            parts.append(f"Clarification requested: {question}")

        return "\n\n".join(p for p in parts if p)
