from __future__ import annotations

from typing import Any

from src.agent.configuration.models import ConfigChange
from src.agent.decision_investigation.models import DecisionEvidence
from src.agent.decision_investigation.state import DecisionInvestigationState


def _get_nested_val(data: dict[str, Any], path: str) -> Any:
    parts = path.split(".")
    curr: Any = data
    for part in parts:
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        else:
            return None
    return curr


class BuildEvidenceNode:
    def __call__(self, state: DecisionInvestigationState) -> dict[str, Any]:
        request = state.get("request")
        refs = (request.references if request and request.references else None) or state.get("references")
        approval = state.get("approval")
        base_config = state.get("base_config")
        resolved_commit = state.get("resolved_commit_hash")
        timeline_items = state.get("timeline_items") or []

        asset = (approval.asset if approval else None) or (refs.asset if refs else None)
        base_commit = (approval.base_commit if approval else None) or (refs.commit_hash if refs else None)

        changes: list[ConfigChange] = []
        risks: list[str] = []
        expected_effect: str | None = None
        proposal_rationale: str | None = None
        consistency_warnings: list[str] = []
        evidence_limitations: list[str] = []

        if approval and approval.proposed_change:
            raw_changes = approval.proposed_change.get("changes", [])
            for ch in raw_changes:
                if isinstance(ch, dict):
                    change_obj = ConfigChange(
                        path=ch.get("path", ""),
                        old_value=ch.get("old_value"),
                        new_value=ch.get("new_value"),
                        reason=ch.get("reason", ""),
                    )
                    changes.append(change_obj)

                    # Consistency check against base_config from VCS
                    if base_config and change_obj.path:
                        actual_val = _get_nested_val(base_config, change_obj.path)
                        if actual_val is not None and str(actual_val) != str(change_obj.old_value):
                            consistency_warnings.append(
                                f"Value mismatch for '{change_obj.path}': proposal says {change_obj.old_value!r}, base commit has {actual_val!r}."
                            )

            risks = approval.proposed_change.get("risks", [])
            expected_effect = approval.proposed_change.get("expected_effect")
            proposal_rationale = approval.description
        else:
            diff_changes = state.get("commit_diff_changes") or []
            if diff_changes:
                if asset:
                    matched = [c for c in diff_changes if f"assets.{asset}" in c.path or c.path == asset]
                    changes = matched if matched else list(diff_changes)
                else:
                    changes = list(diff_changes)
                evidence_limitations.append(
                    "Reconstructed parameter changes directly from VCS commit diff."
                )
            else:
                evidence_limitations.append(
                    f"No persistent approval proposal record found matching asset '{asset}' and commit '{base_commit}'."
                )

        # Filter relevant triggering events from timeline
        triggering_events: list[dict[str, Any]] = []
        for item in timeline_items[:10]:
            category = str(item.get("category", "")).upper()
            title = str(item.get("title", ""))
            summary = str(item.get("summary", ""))
            if any(k in category or k in title.upper() for k in ("STARVATION", "ANOMALY", "APPROVAL", "ERROR", "DECISION", "ORDER")):
                triggering_events.append({
                    "timestamp": item.get("timestamp"),
                    "category": item.get("category"),
                    "title": title,
                    "summary": summary,
                })

        resolved_commit_str = str(resolved_commit) if isinstance(resolved_commit, str) else None
        raw_msg = state.get("commit_message")
        raw_auth = state.get("commit_author")
        commit_message = str(raw_msg) if isinstance(raw_msg, str) else None
        commit_author = str(raw_auth) if isinstance(raw_auth, str) else None

        evidence = DecisionEvidence(
            asset=asset,
            base_commit=base_commit,
            resolved_commit_hash=resolved_commit_str,
            commit_message=commit_message,
            commit_author=commit_author,
            proposed_commit=approval.proposed_config_hash if approval else None,
            approval_id=approval.id if approval else (refs.approval_id if refs else None),
            proposal_id=approval.proposal_id if approval else (refs.proposal_id if refs else None),
            configuration_changes=changes,
            triggering_events=triggering_events,
            proposal_rationale=proposal_rationale or commit_message,
            risks=risks,
            expected_effect=expected_effect,
            approval_status=approval.status.value if approval and hasattr(approval.status, "value") else (str(approval.status) if approval else None),
            consistency_warnings=consistency_warnings,
            evidence_limitations=evidence_limitations,
        )

        return {"evidence": evidence}
