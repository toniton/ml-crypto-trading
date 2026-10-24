from __future__ import annotations
# pylint: disable=too-many-locals

import re
from typing import List, Set, Tuple

from tests.benchmark.agent_20q.models import (
    AdversarialType,
    PromptRunResult,
    QuestionSpec,
    ToolExecutionRecord,
)

# Common numerical / identifier regex patterns
ENTITY_PATTERN = re.compile(
    r"(?:\$[\d,]+(?:\.\d+)?|\b\d+(?:\.\d+)?%|\b(?:ord|dec|tick|exp|ret_run)-[a-zA-Z0-9_\-]+)",
    re.IGNORECASE,
)
COMMON_ALLOWED_TOKENS: Set[str] = {
    "0", "1", "2", "3", "4", "5", "10", "20", "24", "30", "100", "0.0", "1.0", "0%", "100%",
}


class EvidenceGrounder:
    """Verifies agent answers against actual tool outputs and extracts factual grounding metrics."""

    @classmethod
    def evaluate(
        cls,
        spec: QuestionSpec,
        prompt: str,
        response_text: str,
        routed_intent: str,
        invoked_tools: List[str],
        tool_records: List[ToolExecutionRecord],
        latency_ms: float = 0.0,
    ) -> PromptRunResult:
        lower_text = response_text.lower()
        lower_text_no_commas = lower_text.replace(",", "")
        evidence_text = "\n\n".join(r.output_text for r in tool_records if r.output_text)

        # 1. Required facts recall
        matched_facts: List[str] = []
        missing_facts: List[str] = []
        for fact in spec.required_facts:
            fact_low = fact.lower()
            fact_no_commas = fact_low.replace(",", "")
            if fact_low in lower_text or (fact_no_commas and fact_no_commas in lower_text_no_commas):
                matched_facts.append(fact)
            else:
                missing_facts.append(fact)

        # 2. Epistemic phrases & adversarial guardrails
        matched_epistemic: List[str] = []
        missing_epistemic: List[str] = []
        for check in spec.required_epistemic_phrases:
            alternatives = [alt.strip().lower() for alt in check.split("|") if alt.strip()]
            if any(alt in lower_text for alt in alternatives):
                matched_epistemic.append(check)
            else:
                missing_epistemic.append(check)

        # 3. Forbidden hallucinations & contradicted claims
        triggered_hallucinations: List[str] = []
        for forbidden in spec.forbidden_hallucinations:
            if forbidden.lower() in lower_text:
                triggered_hallucinations.append(forbidden)

        # 4. Entity grounding & unsupported claims detection
        grounded_claims, unsupported_claims = cls._extract_and_verify_claims(
            response_text=response_text,
            evidence_text=evidence_text,
            spec=spec,
        )

        contradicted_claims = list(triggered_hallucinations)

        # 5. Tool Selection Score
        tool_selection_score = cls._score_tool_selection(spec, routed_intent, invoked_tools)

        # 6. Epistemic honesty score
        total_epistemic = len(spec.required_epistemic_phrases)
        epistemic_score = (
            len(matched_epistemic) / total_epistemic if total_epistemic > 0 else 1.0
        )
        if spec.is_adversarial and not cls._satisfies_adversarial_contract(spec, lower_text):
            epistemic_score = min(epistemic_score, 0.4)

        # 7. Unsupported claims rate
        total_extracted = len(grounded_claims) + len(unsupported_claims)
        unsupported_rate = (
            len(unsupported_claims) / total_extracted if total_extracted > 0 else 0.0
        )

        # 8. Factual accuracy score
        total_facts = len(spec.required_facts)
        fact_recall = len(matched_facts) / total_facts if total_facts > 0 else 1.0

        if triggered_hallucinations:
            factual_accuracy_score = 0.0
            unsupported_rate = 1.0
        else:
            penalty = 0.25 * min(1.0, len(unsupported_claims)) + (0.5 if missing_facts else 0.0)
            factual_accuracy_score = max(0.0, fact_recall - (penalty * 0.5))

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
            triggered_hallucinations=triggered_hallucinations,
            tool_records=tool_records,
            grounded_claims=grounded_claims,
            unsupported_claims=unsupported_claims,
            contradicted_claims=contradicted_claims,
            tool_selection_score=round(tool_selection_score, 4),
            factual_accuracy_score=round(factual_accuracy_score, 4),
            unsupported_claims_rate=round(unsupported_rate, 4),
            epistemic_honesty_score=round(epistemic_score, 4),
        )

    @classmethod
    def _extract_and_verify_claims(
        cls,
        response_text: str,
        evidence_text: str,
        spec: QuestionSpec,
    ) -> Tuple[List[str], List[str]]:
        matches = ENTITY_PATTERN.findall(response_text)
        grounded: List[str] = []
        unsupported: List[str] = []
        lower_evidence = evidence_text.lower()
        all_prompts_corpus = " ".join(spec.all_prompts).lower()
        known_required = [f.lower() for f in spec.required_facts]

        # Extract numeric values present in evidence, prompt, or required facts
        evidence_numeric_corpus = (
            lower_evidence
            + " "
            + " ".join(known_required)
            + " "
            + all_prompts_corpus
        ).replace(",", "")
        evidence_numbers: Set[float] = set()
        for raw in re.findall(r"[-+]?\d*\.?\d+", evidence_numeric_corpus):
            try:
                parsed = float(raw)
                evidence_numbers.add(parsed)
                evidence_numbers.add(abs(parsed))
            except ValueError:
                pass

        for token in matches:
            t_norm = token.strip().lower()
            t_no_commas = t_norm.replace(",", "")
            if t_norm in COMMON_ALLOWED_TOKENS or t_no_commas in COMMON_ALLOWED_TOKENS:
                continue

            # Check textual containment
            is_textually_grounded = (
                t_norm in lower_evidence
                or t_no_commas in lower_evidence.replace(",", "")
                or t_norm in all_prompts_corpus
                or any(t_norm in rf or rf in t_norm for rf in known_required)
            )

            # Check numerical equivalence
            is_numerically_grounded = False
            clean_num = t_no_commas.lstrip("$+-").rstrip("%")
            try:
                val = float(clean_num)
                abs_val = abs(val)
                is_numerically_grounded = (
                    val in evidence_numbers
                    or abs_val in evidence_numbers
                    or round(abs_val / 100.0, 6) in evidence_numbers
                    or round(abs_val * 100.0, 4) in evidence_numbers
                    or any(abs(abs_val - ev_n) <= 0.1 for ev_n in evidence_numbers)
                )
            except ValueError:
                pass

            if is_textually_grounded or is_numerically_grounded:
                if token not in grounded:
                    grounded.append(token)
            else:
                if token not in unsupported:
                    unsupported.append(token)

        return grounded, unsupported

    @classmethod
    def _score_tool_selection(
        cls,
        spec: QuestionSpec,
        routed_intent: str,
        invoked_tools: List[str],
    ) -> float:
        allowed_intents = {i.value for i in spec.expected_intents}
        intent_ok = 1.0 if not allowed_intents or routed_intent in allowed_intents else 0.0

        if not spec.expected_tools:
            return intent_ok

        matched_tools = sum(1 for t in spec.expected_tools if t in invoked_tools)
        tool_recall = matched_tools / len(spec.expected_tools)

        # Penalize calling completely unrelated tools if invoked_tools has non-expected tools
        excess_tools = [t for t in invoked_tools if t not in spec.expected_tools]
        tool_precision = 1.0 / (1.0 + 0.2 * len(excess_tools))

        return 0.40 * intent_ok + 0.40 * tool_recall + 0.20 * tool_precision

    @classmethod
    def _satisfies_adversarial_contract(cls, spec: QuestionSpec, lower_text: str) -> bool:
        if spec.adversarial_type == AdversarialType.MISSING_DATA:
            indicators = ["not found", "unavailable", "missing", "no record", "does not exist", "unrecognized"]
            return any(ind in lower_text for ind in indicators)
        if spec.adversarial_type == AdversarialType.STALE_DATA:
            indicators = ["stale", "outdated", "last updated", "delay", "expired", "old"]
            return any(ind in lower_text for ind in indicators)
        if spec.adversarial_type == AdversarialType.CONFLICTING_DATA:
            indicators = ["divergence", "conflict", "mismatch", "discrepancy", "disagree"]
            return any(ind in lower_text for ind in indicators)
        if spec.adversarial_type == AdversarialType.FALSE_PRESUPPOSITION:
            indicators = [
                "rejected", "not executed", "did not place", "prevented", "was not executed", "never executed"
            ]
            return any(ind in lower_text for ind in indicators)
        return True
