from __future__ import annotations

from typing import List

from src.agent.events import AIEvent


class ResponseReconstructor:
    def __init__(self):
        self._parts: List[str] = []

    def feed(self, event: AIEvent) -> None:
        part = self._event_text(event)
        if part:
            self._parts.append(part)

    def reconstruct(self) -> str:
        return "".join(self._parts).strip()

    @staticmethod
    def _event_text(event: AIEvent) -> str:
        if event.type == "token" and isinstance(event.payload, str):
            return event.payload
        if event.type == "clarification":
            payload = event.payload
            if isinstance(payload, dict):
                question = payload.get("question")
                return str(question) if question else ""
            return ""
        if event.type == "block":
            return ResponseReconstructor._block_text(event.payload)
        return ""

    @staticmethod
    def _block_text(block) -> str:
        block_type = getattr(block, "type", None)
        if block_type == "markdown":
            return str(getattr(block, "content", "") or "")
        if block_type == "configuration_diff":
            prefix = getattr(block, "prefix", "") or "Proposed changes"
            lines = [prefix]
            for change in getattr(block, "changes", []) or []:
                lines.append(
                    f"- {change.path}: {change.old_value!r} -> {change.new_value!r} ({change.reason})"
                )
            return "\n".join(lines)
        if block_type == "approval":
            return "Awaiting approval of the proposed configuration changes."
        if block_type == "configuration_view":
            lines = [f"# {block.base} / {block.quote} — {block.name}", f"`{block.asset}`"]
            for section in getattr(block, "sections", []) or []:
                lines.append(f"\n## {section.title}")
                for field in getattr(section, "fields", []) or []:
                    lines.append(f"- {field.path}: {field.value!r}")
            return "\n".join(lines)
        if block_type == "clarification":
            return str(getattr(block, "content", "") or "")
        return ""
