from __future__ import annotations

from typing import Any, Optional

from src.agent.decision_investigation.state import DecisionInvestigationState
from src.vcs.application.service import VCSService


class ResolveCommitNode:
    def __init__(self, vcs: Optional[VCSService] = None):
        self._vcs = vcs

    def __call__(self, state: DecisionInvestigationState) -> dict[str, Any]:
        request = state.get("request")
        refs = (request.references if request and request.references else None) or state.get("references")
        approval = state.get("approval")

        commit_ref = (approval.base_commit if approval and approval.base_commit else None) or (refs.commit_hash if refs else None)
        resolved_commit_hash: Optional[str] = None
        commit_message: Optional[str] = None
        commit_author: Optional[str] = None
        base_config: Optional[dict[str, Any]] = None

        if self._vcs and commit_ref:
            try:
                resolved = self._vcs.resolve_commit_hash(commit_ref)
                if isinstance(resolved, str):
                    resolved_commit_hash = resolved
                
                target_hash = resolved_commit_hash or commit_ref
                commit_obj = self._vcs.head(target_hash)
                if commit_obj:
                    msg = getattr(commit_obj, "message", None)
                    auth = getattr(commit_obj, "author", None)
                    if isinstance(msg, str):
                        commit_message = msg
                    if isinstance(auth, str):
                        commit_author = auth

                base = self._vcs.checkout(target_hash)
                if isinstance(base, dict):
                    base_config = base
            except Exception:
                pass

        return {
            "resolved_commit_hash": resolved_commit_hash,
            "commit_message": commit_message,
            "commit_author": commit_author,
            "base_config": base_config,
        }
