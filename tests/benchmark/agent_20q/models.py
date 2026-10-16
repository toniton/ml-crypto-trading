from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from src.agent.router.models import AgentIntent


class QuestionCategory(str, Enum):
    LIVE_OPERATIONS = "Live operations and account state"
    DECISIONS_CONFIG = "Decisions and configuration"
    PERFORMANCE_ATTRIBUTION = "Performance and attribution"
    BACKTESTING_EXPERIMENTS = "Backtesting and experiments"
    RISK_TRACE_GOVERNANCE = "Risk, system behavior, and data governance"


@dataclass(frozen=True)
class QuestionSpec:  # pylint: disable=too-many-instance-attributes
    question_id: str
    number: int
    category: QuestionCategory
    canonical_prompt: str
    paraphrases: list[str]
    expected_intents: list[AgentIntent]
    expected_tools: list[str]
    required_facts: list[str]
    required_epistemic_phrases: list[str]
    forbidden_hallucinations: list[str]
    baseline_readiness: str

    @property
    def all_prompts(self) -> list[str]:
        return [self.canonical_prompt, *self.paraphrases]


@dataclass
class PromptRunResult:  # pylint: disable=too-many-instance-attributes
    prompt: str
    routed_intent: str
    invoked_tools: list[str]
    response_text: str
    latency_ms: float
    matched_facts: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    matched_epistemic: list[str] = field(default_factory=list)
    missing_epistemic: list[str] = field(default_factory=list)
    triggered_hallucinations: list[str] = field(default_factory=list)


@dataclass
class QuestionScore:  # pylint: disable=too-many-instance-attributes
    question_id: str
    title: str
    category: str
    baseline_readiness: str
    route_and_tool_score: float
    fact_recall_score: float
    epistemic_guardrail_score: float
    consistency_score: float
    weighted_total_score: float
    passed: bool
    avg_latency_ms: float
    runs: list[PromptRunResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkSuiteReport:  # pylint: disable=too-many-instance-attributes
    model_id: str
    mode: str
    timestamp: str
    total_questions: int
    passed_questions: int
    pass_rate_pct: float
    mean_score: float
    mean_route_tool_score: float
    mean_fact_recall: float
    mean_epistemic_score: float
    mean_consistency_score: float
    p50_latency_ms: float
    p95_latency_ms: float
    question_scores: list[QuestionScore] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [
            "# Rio 20-Question Acceptance & Grounding Benchmark Report",
            "",
            f"- **Model / Adapter**: `{self.model_id}`",
            f"- **Execution Mode**: `{self.mode}`",
            f"- **Evaluated At**: `{self.timestamp}`",
            f"- **Overall Pass Rate**: **{self.passed_questions}/{self.total_questions} ({self.pass_rate_pct:.1f}%)**",
            f"- **Mean Composite Score**: **{self.mean_score * 100:.1f}%**",
            f"  - Route & Tool Selection (20%): `{self.mean_route_tool_score * 100:.1f}%`",
            f"  - Grounded Fact Recall (40%): `{self.mean_fact_recall * 100:.1f}%`",
            f"  - Epistemic Guardrails (25%): `{self.mean_epistemic_score * 100:.1f}%`",
            f"  - Cross-Prompt Consistency (15%): `{self.mean_consistency_score * 100:.1f}%`",
            f"- **Latency**: `p50 = {self.p50_latency_ms:.1f} ms` | `p95 = {self.p95_latency_ms:.1f} ms`",
            "",
            "## Summary by Question (Q01–Q20)",
            "",
            "| ID | Question | Category | Baseline | Route/Tool | Fact Recall | "
            "Epistemic | Consistency | Total | Status | Latency |",
            "| :- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
        for q in self.question_scores:
            status = "PASS" if q.passed else "FAIL"
            lines.append(
                f"| **{q.question_id}** | {q.title} | {q.category} | {q.baseline_readiness} | "
                f"{q.route_and_tool_score * 100:.0f}% | {q.fact_recall_score * 100:.0f}% | "
                f"{q.epistemic_guardrail_score * 100:.0f}% | {q.consistency_score * 100:.0f}% | "
                f"**{q.weighted_total_score * 100:.1f}%** | **{status}** | {q.avg_latency_ms:.1f}ms |"
            )

        lines.extend([
            "",
            "## Category Breakdown",
            "",
            "| Category | Passed | Mean Fact Recall | Mean Epistemic | Mean Total |",
            "| :--- | :---: | :---: | :---: | :---: |",
        ])
        for cat in QuestionCategory:
            cat_scores = [q for q in self.question_scores if q.category == cat.value]
            if not cat_scores:
                continue
            c_passed = sum(1 for q in cat_scores if q.passed)
            c_fact = sum(q.fact_recall_score for q in cat_scores) / len(cat_scores)
            c_epist = sum(q.epistemic_guardrail_score for q in cat_scores) / len(cat_scores)
            c_tot = sum(q.weighted_total_score for q in cat_scores) / len(cat_scores)
            lines.append(
                f"| **{cat.value}** | {c_passed}/{len(cat_scores)} | {c_fact * 100:.1f}% | "
                f"{c_epist * 100:.1f}% | **{c_tot * 100:.1f}%** |"
            )
        return "\n".join(lines)
