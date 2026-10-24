from __future__ import annotations

import json
from typing import Any, Optional

from src.agent.evidence_proposal.models import NarrativeSynthesis
from src.agent.evidence_proposal.prompts import EVIDENCE_PROPOSAL_WRITER_PROMPT
from src.agent.evidence_proposal.state import EvidenceProposalState
from src.core.interfaces.llm_adapter import LlmAdapter
from src.proposals.markdown_formatter import ProposalMarkdownFormatter


class SynthesizeNarrativeNode:
    def __init__(self, llm: Optional[LlmAdapter] = None):
        self._llm = llm

    def __call__(self, state: EvidenceProposalState) -> dict[str, Any]:
        proposal = state.get("evidence_proposal")
        if proposal is None:
            return {}

        if self._llm is not None:
            try:
                prompt_payload = {
                    "title": proposal.title,
                    "ticker_symbol": proposal.ticker_symbol,
                    "evidence_status": proposal.evidence_status.value,
                    "recommendation": proposal.recommendation.value,
                    "expected_benefit": proposal.expected_benefit.model_dump(mode="json"),
                    "sample_size": proposal.sample_size.model_dump(mode="json"),
                    "uncertainty": proposal.uncertainty.model_dump(mode="json"),
                    "risk_changes": proposal.risk_changes.model_dump(mode="json"),
                    "limitations": proposal.limitations,
                    "validation_plan": proposal.validation_plan,
                }
                synthesis: NarrativeSynthesis = self._llm.generate_structured(
                    schema=NarrativeSynthesis,
                    prompt=(
                        f"User request: {state.get('user_prompt', '')}\n\n"
                        f"Deterministic evaluation data:\n{json.dumps(prompt_payload, indent=2)}"
                    ),
                    system_prompt=EVIDENCE_PROPOSAL_WRITER_PROMPT,
                )
                if isinstance(synthesis, NarrativeSynthesis):
                    if synthesis.hypothesis.strip():
                        proposal.hypothesis = synthesis.hypothesis.strip()
                    if synthesis.executive_summary.strip():
                        proposal.narrative_summary = synthesis.executive_summary.strip()
                        proposal.narrative_summary = ProposalMarkdownFormatter.format_proposal(
                            proposal
                        )
            except Exception:  # pylint: disable=broad-except
                pass

        return {"evidence_proposal": proposal}
