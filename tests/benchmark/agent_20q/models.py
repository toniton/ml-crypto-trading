from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from src.agent.router.models import AgentIntent


class QuestionCategory(str, Enum):
    LIVE_OPERATIONS = "Live operations and account state"
    DECISIONS_CONFIG = "Decisions and configuration"
    PERFORMANCE_ATTRIBUTION = "Performance and attribution"
    BACKTESTING_EXPERIMENTS = "Backtesting and experiments"
    RISK_TRACE_GOVERNANCE = "Risk, system behavior, and data governance"
    ADVERSARIAL_ROBUSTNESS = "Adversarial and robustness"


class AdversarialType(str, Enum):
    MISSING_DATA = "missing_data"
    STALE_DATA = "stale_data"
    CONFLICTING_DATA = "conflicting_data"
    FALSE_PRESUPPOSITION = "false_presupposition"


@dataclass(frozen=True)
class ToolExecutionRecord:
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    output: Any = None
    output_text: str = ""
    latency_ms: float = 0.0
    status: str = "success"
    error_message: Optional[str] = None


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
    is_adversarial: bool = False
    adversarial_type: Optional[AdversarialType] = None

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
    tool_records: list[ToolExecutionRecord] = field(default_factory=list)
    grounded_claims: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    contradicted_claims: list[str] = field(default_factory=list)
    tool_selection_score: float = 1.0
    factual_accuracy_score: float = 1.0
    unsupported_claims_rate: float = 0.0
    epistemic_honesty_score: float = 1.0


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
    tool_selection_score: float = 1.0
    factual_accuracy_score: float = 1.0
    unsupported_claims_rate: float = 0.0
    epistemic_honesty_score: float = 1.0
    trial_variance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkProvenance:
    git_commit: str = ""
    git_branch: str = ""
    git_dirty: bool = False
    model_id: str = ""
    provider: str = ""
    temperature: float = 0.0
    suite_version: str = "2.0"
    dataset_hash: str = ""
    tool_manifest: dict[str, str] = field(default_factory=dict)
    evaluated_at: str = ""
    python_version: str = ""


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
    provenance: Optional[BenchmarkProvenance] = None
    num_trials: int = 1
    mean_tool_selection_score: float = 1.0
    mean_factual_accuracy: float = 1.0
    mean_unsupported_claims_rate: float = 0.0
    mean_epistemic_honesty: float = 1.0
    quality_gate_passed: bool = True
    quality_gate_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        gate_status = "PASSED" if self.quality_gate_passed else "FAILED"
        lines = [
            "# Rio Agent Grounding & Quality Gate Benchmark Report",
            "",
            f"- **Quality Gate Verdict**: **{gate_status}**",
            f"- **Model / Adapter**: `{self.model_id}`",
            f"- **Execution Mode**: `{self.mode}` (trials: `{self.num_trials}`)",
            f"- **Evaluated At**: `{self.timestamp}`",
        ]

        if self.provenance:
            dirty_str = " (dirty)" if self.provenance.git_dirty else ""
            lines.extend([
                f"- **Git Revision**: `{self.provenance.git_commit[:9]}` on `{self.provenance.git_branch}`{dirty_str}",
                f"- **Suite Version**: `{self.provenance.suite_version}` | Python `{self.provenance.python_version}`",
            ])

        lines.extend([
            f"- **Overall Pass Rate**: **{self.passed_questions}/{self.total_questions} ({self.pass_rate_pct:.1f}%)**",
            f"- **Mean Composite Score**: **{self.mean_score * 100:.1f}%**",
            f"  - Tool Selection & Routing: `{self.mean_tool_selection_score * 100:.1f}%`",
            f"  - Factual Accuracy (Tool Grounded): `{self.mean_factual_accuracy * 100:.1f}%`",
            f"  - Unsupported Claims Rate: `{self.mean_unsupported_claims_rate * 100:.1f}%`",
            f"  - Epistemic Honesty: `{self.mean_epistemic_honesty * 100:.1f}%`",
            f"  - Consistency (Cross-Prompt & Trials): `{self.mean_consistency_score * 100:.1f}%`",
            f"- **Latency**: `p50 = {self.p50_latency_ms:.1f} ms` | `p95 = {self.p95_latency_ms:.1f} ms`",
        ])

        if self.quality_gate_reasons:
            lines.extend(["", "### Quality Gate Failure Reasons:"])
            for r in self.quality_gate_reasons:
                lines.append(f"- ❌ {r}")

        lines.extend([
            "",
            "## Summary by Question",
            "",
            "| ID | Question | Category | Tool Selection | Fact Accuracy | "
            "Epistemic | Unsupported | Consistency | Total | Status | Latency |",
            "| :- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ])
        for q in self.question_scores:
            status = "PASS" if q.passed else "FAIL"
            lines.append(
                f"| **{q.question_id}** | {q.title} | {q.category} | "
                f"{q.tool_selection_score * 100:.0f}% | {q.factual_accuracy_score * 100:.0f}% | "
                f"{q.epistemic_honesty_score * 100:.0f}% | {q.unsupported_claims_rate * 100:.0f}% | "
                f"{q.consistency_score * 100:.0f}% | "
                f"**{q.weighted_total_score * 100:.1f}%** | **{status}** | {q.avg_latency_ms:.1f}ms |"
            )

        lines.extend([
            "",
            "## Category Breakdown",
            "",
            "| Category | Passed | Mean Tool Sel | Mean Fact Acc | Mean Epistemic | Mean Unsupported | Mean Total |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
        ])
        for cat in QuestionCategory:
            cat_scores = [q for q in self.question_scores if q.category == cat.value]
            if not cat_scores:
                continue
            c_passed = sum(1 for q in cat_scores if q.passed)
            c_tool = sum(q.tool_selection_score for q in cat_scores) / len(cat_scores)
            c_fact = sum(q.factual_accuracy_score for q in cat_scores) / len(cat_scores)
            c_epist = sum(q.epistemic_honesty_score for q in cat_scores) / len(cat_scores)
            c_unsupp = sum(q.unsupported_claims_rate for q in cat_scores) / len(cat_scores)
            c_tot = sum(q.weighted_total_score for q in cat_scores) / len(cat_scores)
            lines.append(
                f"| **{cat.value}** | {c_passed}/{len(cat_scores)} | {c_tool * 100:.1f}% | {c_fact * 100:.1f}% | "
                f"{c_epist * 100:.1f}% | {c_unsupp * 100:.1f}% | **{c_tot * 100:.1f}%** |"
            )
        return "\n".join(lines)
