from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from src.agent.decision_investigation.state import DecisionInvestigationState
from src.server.timeline_projector import TimelineProjector


class LoadTimelineNode:
    def __init__(self, timeline_projector: Optional[TimelineProjector] = None):
        self._timeline_projector = timeline_projector

    def __call__(self, state: DecisionInvestigationState) -> dict[str, Any]:
        if not self._timeline_projector:
            return {"timeline_items": []}

        request = state.get("request")
        refs = (request.references if request and request.references else None) or state.get("references")
        approval = state.get("approval")
        resolved_commit = state.get("resolved_commit_hash")

        asset = (approval.asset if approval else None) or (refs.asset if refs else None)
        commit_candidates = {
            c for c in [
                resolved_commit,
                approval.base_commit if approval else None,
                refs.commit_hash if refs else None,
            ] if c
        }
        approval_id = approval.id if approval else (refs.approval_id if refs else None)

        since = None
        until = None
        if approval and approval.requested_at:
            since = approval.requested_at - timedelta(minutes=15)
            until = approval.requested_at + timedelta(minutes=2)

        items_map: dict[str, dict[str, Any]] = {}

        try:
            if asset:
                for it in self._timeline_projector.list_items(entity_type="ASSET", entity_id=asset, since=since, until=until, limit=20):
                    items_map[it.get("id") or str(len(items_map))] = it

            for commit_val in commit_candidates:
                for it in self._timeline_projector.list_items(entity_type="COMMIT", entity_id=commit_val, limit=10):
                    items_map[it.get("id") or str(len(items_map))] = it

            if approval_id:
                for it in self._timeline_projector.list_items(entity_type="APPROVAL", entity_id=approval_id, limit=10):
                    items_map[it.get("id") or str(len(items_map))] = it

            if not items_map:
                for it in self._timeline_projector.list_items(limit=20):
                    items_map[it.get("id") or str(len(items_map))] = it
        except Exception:
            pass

        return {"timeline_items": list(items_map.values())}
