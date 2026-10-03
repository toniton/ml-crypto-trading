from __future__ import annotations

import re
from typing import Any, Optional

from src.agent.router.models import AgentReferences
from src.agent.router.state import RouterState

_COMMIT_HASH_PATTERN = re.compile(r"(?:Base:\s*|commit[:\s]+)?\b([0-9a-f]{7,40})\b", re.IGNORECASE)
_ASSET_PATTERN = re.compile(r"\b([A-Z0-9]{2,10}[_/][A-Z0-9]{2,10})\b")
_PROPOSAL_PATTERN = re.compile(r"\b(prop-[a-f0-9]+)\b", re.IGNORECASE)
_APPROVAL_PATTERN = re.compile(r"\b(appr-[a-f0-9]+)\b", re.IGNORECASE)


def extract_deterministic_references(prompt: str) -> AgentReferences:
    asset: Optional[str] = None
    commit_hash: Optional[str] = None
    proposal_id: Optional[str] = None
    approval_id: Optional[str] = None

    asset_match = _ASSET_PATTERN.search(prompt)
    if asset_match:
        asset = asset_match.group(1).replace("/", "_").upper()

    commit_match = _COMMIT_HASH_PATTERN.search(prompt)
    if commit_match:
        commit_hash = commit_match.group(1).lower()

    prop_match = _PROPOSAL_PATTERN.search(prompt)
    if prop_match:
        proposal_id = prop_match.group(1)

    appr_match = _APPROVAL_PATTERN.search(prompt)
    if appr_match:
        approval_id = appr_match.group(1)

    return AgentReferences(
        asset=asset,
        commit_hash=commit_hash,
        proposal_id=proposal_id,
        approval_id=approval_id,
    )


class ExtractReferencesNode:
    def __call__(self, state: RouterState) -> dict[str, Any]:
        prompt = state.get("user_prompt", "")
        references = extract_deterministic_references(prompt)
        return {"references": references}
