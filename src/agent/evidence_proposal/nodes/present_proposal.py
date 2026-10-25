from __future__ import annotations

from typing import Any, Optional

from api.interfaces.evidence_proposal import ProposalRecommendation
from src.agent.configuration.models import (
    ApprovalBlock,
    ConfigurationDiffBlock,
    ConfigurationPresentation,
    MarkdownBlock,
    UIBlock,
)
from src.agent.evidence_proposal.state import EvidenceProposalState
from src.core.interfaces.database_manager import DatabaseManager
from src.database.repositories.providers.postgres_evidence_proposal_repository import (
    PostgresEvidenceProposalRepository,
)


class PresentProposalNode:
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self._db_manager = db_manager

    def __call__(self, state: EvidenceProposalState) -> dict[str, Any]:
        resolution_status = state.get("resolution_status")
        status_message = state.get("status_message")

        if resolution_status == "NEEDS_CLARIFICATION":
            msg = status_message or "Please specify the target asset and experiment ID or candidate commit to evaluate."
            return {
                "presentation": ConfigurationPresentation(
                    blocks=[MarkdownBlock.from_text(f"### ❓ Clarification Needed\n\n{msg}")]
                ),
                "evidence_proposal": None,
            }

        if resolution_status == "EVIDENCE_UNAVAILABLE":
            msg = status_message or "Requested evidence was unavailable."
            return {
                "presentation": ConfigurationPresentation(
                    blocks=[MarkdownBlock.from_text(f"### ⚠️ Evidence Unavailable\n\n{msg}")]
                ),
                "evidence_proposal": None,
            }

        proposal = state.get("evidence_proposal")
        collected = state.get("collected_evidence")
        if proposal is None:
            return {"presentation": ConfigurationPresentation.empty()}

        if self._db_manager is not None:
            try:
                with self._db_manager.get_unit_of_work() as uow:
                    repo = uow.get_repository(PostgresEvidenceProposalRepository)
                    repo.save_proposal(proposal)
            except Exception:  # pylint: disable=broad-except
                pass

        blocks: list[UIBlock] = [
            MarkdownBlock.from_text(proposal.narrative_summary),
        ]

        if collected and collected.config_changes:
            blocks.append(
                ConfigurationDiffBlock(
                    changes=collected.config_changes,
                    prefix="Proposed Configuration Diff",
                )
            )

        if (
            proposal.recommendation == ProposalRecommendation.PROMOTE_TO_APPROVAL
            and proposal.candidate_commit
        ):
            blocks.append(ApprovalBlock.build())

        return {
            "presentation": ConfigurationPresentation(blocks=blocks),
            "evidence_proposal": proposal,
        }
