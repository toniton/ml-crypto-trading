from __future__ import annotations

from typing import Any, Optional

from src.agent.actions.models import AgentApprovalRequest, ApprovalStatus
from src.agent.actions.service import AgentApprovalService
from src.agent.decision_investigation.state import DecisionInvestigationState
from src.server.timeline_projector import TimelineProjector


class ResolveProposalNode:
    def __init__(
            self,
            approval_service: Optional[AgentApprovalService] = None,
            timeline_projector: Optional[TimelineProjector] = None,
    ):
        self._approval_service = approval_service
        self._timeline_projector = timeline_projector

    def __call__(self, state: DecisionInvestigationState) -> dict[str, Any]:
        request = state.get("request")
        refs = (request.references if request and request.references else None) or state.get("references")
        approval: Optional[AgentApprovalRequest] = None

        if self._approval_service and refs:
            approval = self._approval_service.find_approval(
                approval_id=refs.approval_id,
                commit_hash=refs.commit_hash,
                asset=refs.asset,
                proposal_id=refs.proposal_id,
            )

        if not approval and self._timeline_projector and refs:
            approval = self._resolve_from_timeline_projector(refs)

        return {"approval": approval}

    def _resolve_from_timeline_projector(self, refs: Any) -> Optional[AgentApprovalRequest]:
        try:
            candidates: list[dict[str, Any]] = []
            if refs.approval_id:
                candidates.extend(self._timeline_projector.list_items(entity_type="APPROVAL", entity_id=refs.approval_id, limit=10))
            if refs.commit_hash:
                candidates.extend(self._timeline_projector.list_items(entity_type="COMMIT", entity_id=refs.commit_hash, limit=20))
            
            # Always query approval category directly so high-frequency consensus events do not crowd out proposals
            candidates.extend(self._timeline_projector.list_items(category="APPROVAL", limit=50))

            if refs.asset:
                candidates.extend(self._timeline_projector.list_items(entity_type="ASSET", entity_id=refs.asset, limit=20))

            target_hash = refs.commit_hash.lower() if refs.commit_hash else None
            target_asset = refs.asset.upper() if refs.asset else None

            for item in candidates:
                meta = item.get("metadata") or {}
                if not isinstance(meta, dict):
                    continue

                proposed_change = meta.get("proposed_change") or (
                    {"changes": meta["changes"]} if "changes" in meta and isinstance(meta["changes"], list) else None
                )
                if not proposed_change:
                    continue

                item_commit = str(meta.get("base_commit", "")).lower()
                item_asset = str(meta.get("asset", "")).upper()

                match_commit = target_hash is None or (
                        item_commit and (item_commit.startswith(target_hash) or target_hash.startswith(item_commit))
                )
                match_asset = target_asset is None or (item_asset == target_asset)

                if match_commit and match_asset:
                    status_val = str(meta.get("status", "pending")).upper()
                    try:
                        status = ApprovalStatus(status_val)
                    except ValueError:
                        status = ApprovalStatus.PENDING

                    return AgentApprovalRequest(
                        id=str(meta.get("id") or meta.get("approval_id") or item.get("id")),
                        agent_action_id=str(meta.get("agent_action_id") or "action"),
                        action_type=meta.get("action_type") or "CREATE_PROPOSAL",
                        title=meta.get("title") or item.get("title") or "Approval Request",
                        description=meta.get("description") or item.get("summary") or "",
                        proposed_change=proposed_change if isinstance(proposed_change, dict) else {"changes": proposed_change},
                        base_commit=meta.get("base_commit") or (refs.commit_hash or ""),
                        asset=meta.get("asset") or refs.asset,
                        status=status,
                    )
        except Exception:
            pass
        return None
