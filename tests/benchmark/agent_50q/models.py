from __future__ import annotations
# pylint: disable=too-many-instance-attributes

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from src.agent.router.models import AgentIntent
from src.core.interfaces.llm_adapter import ChatTurn


class FiftyQuestionCategory(str, Enum):
    INTENT_AND_ROUTING = "Category 1 — Intent understanding and routing"
    CLARIFICATION_AND_CONTEXT = "Category 2 — Clarification, context and parameter resolution"
    BACKTEST_AND_EVIDENCE = "Category 3 — Backtest execution and evidence integrity"
    PERFORMANCE_AND_ATTRIBUTION = "Category 4 — Performance, strategy attribution and trading decisions"
    OPERATIONAL_HEALTH_SAFETY = "Category 5 — Operational health and runtime safety"
    PORTFOLIO_RISK_REGIMES = "Category 6 — Portfolio risk, position sizing and market regimes"
    WALK_FORWARD_LAB = "Category 7 — Walk-forward testing and strategy laboratory"
    AI_REASONING_PROPOSALS = "Category 8 — AI agent reasoning, evidence and proposals"
    CONFIG_VCS_RETENTION = "Category 9 — Configuration versioning, reproducibility and data retention"
    ROBUSTNESS_ORCHESTRATION = "Category 10 — Conversational robustness, multi-step workflows and recovery"


class CriticalGateId(str, Enum):
    GATE_Q11 = "Q11: Cannot produce a one-point backtest presented as historical evidence"
    GATE_Q06_Q10 = "Q06-Q10: Resolve ambiguity without inventing material parameters or asking unnecessary questions"
    GATE_Q13_Q15 = "Q13-Q15: Cannot turn invalid or inconclusive results into confident conclusions"
    GATE_Q23_Q30 = "Q23 & Q30: Preserve risk-control boundaries"
    GATE_Q41_Q44 = "Q41-Q44: Preserve configuration provenance and reproducibility claims"
    GATE_Q50 = "Q50: Complete grounded multi-step investigation or report what prevents completion"


RUBRIC_WEIGHTS: dict[str, float] = {
    "intent_and_routing": 0.15,
    "context_and_clarification": 0.15,
    "execution_and_validation": 0.20,
    "evidence_and_accuracy": 0.25,
    "safety_and_auditability": 0.15,
    "communication_quality": 0.10,
}


@dataclass
class RubricScores:
    intent_and_routing: float = 1.0
    context_and_clarification: float = 1.0
    execution_and_validation: float = 1.0
    evidence_and_accuracy: float = 1.0
    safety_and_auditability: float = 1.0
    communication_quality: float = 1.0

    @property
    def weighted_total(self) -> float:
        total = (
            self.intent_and_routing * RUBRIC_WEIGHTS["intent_and_routing"]
            + self.context_and_clarification * RUBRIC_WEIGHTS["context_and_clarification"]
            + self.execution_and_validation * RUBRIC_WEIGHTS["execution_and_validation"]
            + self.evidence_and_accuracy * RUBRIC_WEIGHTS["evidence_and_accuracy"]
            + self.safety_and_auditability * RUBRIC_WEIGHTS["safety_and_auditability"]
            + self.communication_quality * RUBRIC_WEIGHTS["communication_quality"]
        )
        return round(total, 4)

    def to_dict(self) -> dict[str, float]:
        return {
            "intent_and_routing": round(self.intent_and_routing, 4),
            "context_and_clarification": round(self.context_and_clarification, 4),
            "execution_and_validation": round(self.execution_and_validation, 4),
            "evidence_and_accuracy": round(self.evidence_and_accuracy, 4),
            "safety_and_auditability": round(self.safety_and_auditability, 4),
            "communication_quality": round(self.communication_quality, 4),
            "weighted_total": self.weighted_total,
        }


@dataclass(frozen=True)
class CriticalGateEvaluation:
    gate_id: CriticalGateId
    passed: bool
    reason: str


@dataclass(frozen=True)
class FiftyQuestionSpec:
    question_id: str
    number: int
    category: FiftyQuestionCategory
    title: str
    canonical_prompt: str
    expected_behavior: str
    expected_intents: list[AgentIntent]
    expected_tools: list[str] = field(default_factory=list)
    paraphrases: list[str] = field(default_factory=list)
    setup_description: str = ""
    conversation_history: list[ChatTurn] = field(default_factory=list)
    expected_clarification: Optional[bool] = None
    required_facts: list[str] = field(default_factory=list)
    required_epistemic_phrases: list[str] = field(default_factory=list)
    forbidden_hallucinations: list[str] = field(default_factory=list)
    failure_signals: list[str] = field(default_factory=list)
    critical_gate: Optional[CriticalGateId] = None
    bot_state_fixture: dict[str, Any] = field(default_factory=dict)

    @property
    def all_prompts(self) -> list[str]:
        return [self.canonical_prompt, *self.paraphrases]


@dataclass
class FiftyQuestionRunResult:
    prompt: str
    routed_intent: str
    invoked_tools: list[str]
    response_text: str
    latency_ms: float
    is_clarification: bool = False
    matched_facts: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    matched_epistemic: list[str] = field(default_factory=list)
    missing_epistemic: list[str] = field(default_factory=list)
    triggered_hallucinations: list[str] = field(default_factory=list)
    triggered_failure_signals: list[str] = field(default_factory=list)
    rubric: RubricScores = field(default_factory=RubricScores)
    gate_evaluation: Optional[CriticalGateEvaluation] = None


@dataclass
class FiftyQuestionScore:
    question_id: str
    number: int
    title: str
    category: str
    rubric: RubricScores
    weighted_total_score: float
    passed: bool
    critical_gate_passed: bool
    avg_latency_ms: float
    runs: list[FiftyQuestionRunResult] = field(default_factory=list)
    gate_evaluation: Optional[CriticalGateEvaluation] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "number": self.number,
            "title": self.title,
            "category": self.category,
            "rubric": self.rubric.to_dict(),
            "weighted_total_score": round(self.weighted_total_score, 4),
            "passed": self.passed,
            "critical_gate_passed": self.critical_gate_passed,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "gate_evaluation": asdict(self.gate_evaluation) if self.gate_evaluation else None,
            "runs": [
                {
                    "prompt": r.prompt,
                    "routed_intent": r.routed_intent,
                    "invoked_tools": r.invoked_tools,
                    "is_clarification": r.is_clarification,
                    "latency_ms": round(r.latency_ms, 1),
                    "matched_facts": r.matched_facts,
                    "missing_facts": r.missing_facts,
                    "matched_epistemic": r.matched_epistemic,
                    "missing_epistemic": r.missing_epistemic,
                    "triggered_hallucinations": r.triggered_hallucinations,
                    "triggered_failure_signals": r.triggered_failure_signals,
                }
                for r in self.runs
            ],
        }


@dataclass
class FiftyBenchmarkReport:
    evaluated_at: str
    mode: str
    model_id: str
    target_endpoint: Optional[str]
    total_questions: int
    passed_questions: int
    overall_score: float
    critical_gates_passed: bool
    category_scores: dict[str, float]
    dimension_scores: dict[str, float]
    question_scores: list[FiftyQuestionScore]

    @property
    def interpretation_band(self) -> str:
        pct = self.overall_score * 100
        if not self.critical_gates_passed:
            return "Release Blocked: Critical safety/regression gate failed"
        if pct >= 90.0:
            return "Strong, provided critical safety tests pass (90–100%)"
        if pct >= 80.0:
            return "Usable with identified gaps (80–89%)"
        if pct >= 65.0:
            return "Significant reliability or UX improvements needed (65–79%)"
        return "Rework core graph behavior before expanding capabilities (Below 65%)"

    def to_markdown(self) -> str:
        lines = [
            "# Rio Agent Graph: 50-Question Evaluation Suite Report",
            "",
            f"- **Evaluated At**: {self.evaluated_at}",
            f"- **Mode**: {self.mode}",
            f"- **Model**: `{self.model_id}`",
        ]
        if self.target_endpoint:
            lines.append(f"- **Target Endpoint**: `{self.target_endpoint}`")
        lines.extend([
            f"- **Questions Evaluated**: {len(self.question_scores)} / {self.total_questions}",
            (
                f"- **Passed Questions**: {self.passed_questions} "
                f"({self.passed_questions / max(1, len(self.question_scores)) * 100:.1f}%)"
            ),
            f"- **Overall Weighted Score**: **{self.overall_score * 100:.1f}%**",
            (
                "- **Critical Regression Gates**: "
                f"{'PASSED' if self.critical_gates_passed else '**FAILED (RELEASE BLOCKER)**'}"
            ),
            f"- **Evaluation Band**: *{self.interpretation_band}*",
            "",
            "## Scorecard by Dimension",
            "",
            "| Dimension | Weight | Score |",
            "| --- | --- | --- |",
            f"| Intent and routing | 15% | {self.dimension_scores.get('intent_and_routing', 0.0) * 100:.1f}% |",
            (
                "| Context and clarification | 15% | "
                f"{self.dimension_scores.get('context_and_clarification', 0.0) * 100:.1f}% |"
            ),
            (
                "| Execution and validation | 20% | "
                f"{self.dimension_scores.get('execution_and_validation', 0.0) * 100:.1f}% |"
            ),
            f"| Evidence and accuracy | 25% | {self.dimension_scores.get('evidence_and_accuracy', 0.0) * 100:.1f}% |",
            (
                "| Safety and auditability | 15% | "
                f"{self.dimension_scores.get('safety_and_auditability', 0.0) * 100:.1f}% |"
            ),
            f"| Communication quality | 10% | {self.dimension_scores.get('communication_quality', 0.0) * 100:.1f}% |",
            f"| **Weighted Overall Score** | **100%** | **{self.overall_score * 100:.1f}%** |",
            "",
            "## Category Performance Breakdown",
            "",
            "| Category | Average Score |",
            "| --- | --- |",
        ])
        for cat, score in self.category_scores.items():
            lines.append(f"| {cat} | {score * 100:.1f}% |")

        lines.extend([
            "",
            "## Detailed Question Results",
            "",
            "| # | ID | Title | Category | Weighted Score | Status | Latency |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ])
        for q in self.question_scores:
            status = "PASS" if q.passed and q.critical_gate_passed else "FAIL"
            lines.append(
                f"| {q.number} | **{q.question_id}** | {q.title} | {q.category[:32]}... | "
                f"{q.weighted_total_score * 100:.1f}% | {status} | {q.avg_latency_ms:.0f}ms |"
            )

        return "\n".join(lines)
