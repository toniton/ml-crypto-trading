from __future__ import annotations
# pylint: disable=too-many-locals

from datetime import datetime, timezone
import statistics
import time
from typing import Any, Optional

from src.agent.gateway import AgentGateway
from src.core.interfaces.llm_adapter import LlmAdapter
from tests.benchmark.agent_20q.models import (
    BenchmarkSuiteReport,
    PromptRunResult,
    QuestionScore,
    QuestionSpec,
)
from tests.benchmark.agent_20q.scenarios import (
    TWENTY_QUESTIONS,
    SeededBenchmarkEnvironment,
    build_seeded_environment,
)
from tests.benchmark.agent_20q.scripted_llm import BenchmarkScriptedLlmAdapter


class TwentyQuestionsEvaluator:
    def __init__(
            self,
            env: Optional[SeededBenchmarkEnvironment] = None,
            llm_adapter: Optional[LlmAdapter] = None,
            mode: str = "deterministic",
            model_id: str = "scripted-deterministic-v1",
    ) -> None:
        self.env = env or build_seeded_environment()
        self.llm: LlmAdapter = llm_adapter or BenchmarkScriptedLlmAdapter(self.env)
        self.mode = mode
        self.model_id = model_id
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
    ) -> BenchmarkSuiteReport:
        specs = questions or TWENTY_QUESTIONS
        scores = [
            self.evaluate_question(spec, include_paraphrases=include_paraphrases)
            for spec in specs
        ]
        total_q = len(scores)
        passed_q = sum(1 for s in scores if s.passed)
        pass_rate = (passed_q / total_q * 100.0) if total_q else 0.0
        mean_score = sum(s.weighted_total_score for s in scores) / total_q if total_q else 0.0
        mean_route = sum(s.route_and_tool_score for s in scores) / total_q if total_q else 0.0
        mean_fact = sum(s.fact_recall_score for s in scores) / total_q if total_q else 0.0
        mean_epist = sum(s.epistemic_guardrail_score for s in scores) / total_q if total_q else 0.0
        mean_cons = sum(s.consistency_score for s in scores) / total_q if total_q else 0.0

        all_latencies = [r.latency_ms for s in scores for r in s.runs] or [0.0]
        sorted_lat = sorted(all_latencies)
        p50 = statistics.median(sorted_lat)
        p95_idx = min(len(sorted_lat) - 1, int(len(sorted_lat) * 0.95))
        p95 = sorted_lat[p95_idx]

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
        )

    def evaluate_question(
            self,
            spec: QuestionSpec,
            include_paraphrases: bool = True,
    ) -> QuestionScore:
        prompts = spec.all_prompts if include_paraphrases else [spec.canonical_prompt]
        prompt_results = [self.evaluate_prompt(spec, prompt) for prompt in prompts]
        return self.score_question(spec, prompt_results)

    def evaluate_prompt(self, spec: QuestionSpec, prompt: str) -> PromptRunResult:
        if isinstance(self.llm, BenchmarkScriptedLlmAdapter):
            self.llm.reset_turn_tracking()

        start_ns = time.perf_counter_ns()
        result = self.gateway.handle(prompt, history=[])
        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0

        response_text = self._extract_presentation_text(result)
        invoked_tools = (
            list(self.llm.invoked_tools)
            if isinstance(self.llm, BenchmarkScriptedLlmAdapter)
            else []
        )
        routed_intent = (
            self.llm.routed_intent or getattr(result, "kind", "")
            if isinstance(self.llm, BenchmarkScriptedLlmAdapter)
            else getattr(result, "kind", "")
        )

        return self.grade_response(
            spec=spec,
            prompt=prompt,
            response_text=response_text,
            routed_intent=routed_intent,
            invoked_tools=invoked_tools,
            latency_ms=elapsed_ms,
        )

    @staticmethod
    def grade_response(
            spec: QuestionSpec,
            prompt: str,
            response_text: str,
            routed_intent: str,
            invoked_tools: list[str],
            latency_ms: float = 0.0,
    ) -> PromptRunResult:
        lower_text = response_text.lower()

        matched_facts: list[str] = []
        missing_facts: list[str] = []
        for fact in spec.required_facts:
            if fact.lower() in lower_text:
                matched_facts.append(fact)
            else:
                missing_facts.append(fact)

        matched_epistemic: list[str] = []
        missing_epistemic: list[str] = []
        for check in spec.required_epistemic_phrases:
            alternatives = [alt.strip().lower() for alt in check.split("|") if alt.strip()]
            if any(alt in lower_text for alt in alternatives):
                matched_epistemic.append(check)
            else:
                missing_epistemic.append(check)

        hallucinations: list[str] = []
        for forbidden in spec.forbidden_hallucinations:
            if forbidden.lower() in lower_text:
                hallucinations.append(forbidden)

        return PromptRunResult(
            prompt=prompt,
            routed_intent=routed_intent,
            invoked_tools=invoked_tools,
            response_text=response_text,
            latency_ms=latency_ms,
            matched_facts=matched_facts,
            missing_facts=missing_facts,
            matched_epistemic=matched_epistemic,
            missing_epistemic=missing_epistemic,
            triggered_hallucinations=hallucinations,
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
        hallucination_detected = False

        for run in prompt_results:
            if run.triggered_hallucinations:
                hallucination_detected = True

            intent_ok = 1.0 if run.routed_intent in allowed_intents else 0.0
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

        avg_route = sum(route_scores) / len(route_scores)
        avg_fact = sum(fact_scores) / len(fact_scores)
        avg_epistemic = sum(epistemic_scores) / len(epistemic_scores)

        all_runs_complete = all(
            not r.missing_facts
            and not r.missing_epistemic
            and not r.triggered_hallucinations
            and r.routed_intent in allowed_intents
            for r in prompt_results
        )
        consistency = 1.0 if all_runs_complete else min(avg_fact, avg_epistemic)

        if hallucination_detected:
            avg_fact = 0.0
            avg_epistemic = 0.0
            consistency = 0.0
            weighted_total = 0.0
            passed = False
        else:
            weighted_total = (
                    0.20 * avg_route
                    + 0.40 * avg_fact
                    + 0.25 * avg_epistemic
                    + 0.15 * consistency
            )
            passed = (
                    weighted_total >= 0.85
                    and avg_fact >= 0.80
                    and avg_epistemic >= 0.80
                    and consistency >= 0.80
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

        return "\n\n".join(p for p in parts if p)
