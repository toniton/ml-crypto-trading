from __future__ import annotations

from typing import Any, List, Optional

from src.agent.configuration.models import (
    ApprovalBlock,
    ConfigurationDiffBlock,
    ConfigurationViewBlock,
    MarkdownBlock,
)
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

    @classmethod
    def _block_text(cls, block: Any) -> str:
        model_result = cls._model_block_text(block)
        if model_result is not None:
            return model_result
        if isinstance(block, dict):
            return cls._dict_block_text(block)
        return ""

    @staticmethod
    def _model_block_text(block: Any) -> Optional[str]:
        if isinstance(block, MarkdownBlock):
            return str(block.content or "")
        if isinstance(block, ConfigurationDiffBlock):
            prefix = block.prefix or "Proposed changes"
            lines = [prefix]
            for change in block.changes:
                lines.append(
                    f"- {change.path}: {change.old_value!r} -> {change.new_value!r} ({change.reason})"
                )
            return "\n".join(lines)
        if isinstance(block, ApprovalBlock):
            return "Awaiting approval of the proposed configuration changes."
        if isinstance(block, ConfigurationViewBlock):
            lines = [f"# {block.base} / {block.quote} — {block.name}", f"`{block.asset}`"]
            for section in block.sections:
                lines.append(f"\n## {section.title}")
                for field in section.fields:
                    lines.append(f"- {field.path}: {field.value!r}")
            return "\n".join(lines)
        return None

    @classmethod
    def _dict_block_text(cls, block: dict) -> str:
        block_type = block.get("type")
        if block_type in ("markdown", "clarification"):
            return str(block.get("content", ""))
        if block_type == "approval":
            return "Awaiting approval of the proposed configuration changes."
        if block_type == "configuration_diff":
            return cls._dict_diff_text(block)
        if block_type == "configuration_view":
            return cls._dict_view_text(block)
        return ""

    @staticmethod
    def _dict_diff_text(block: dict) -> str:
        prefix = block.get("prefix") or "Proposed changes"
        lines = [prefix]
        for change in block.get("changes", []):
            path = change.get("path") if isinstance(change, dict) else change.path
            old_v = change.get("old_value") if isinstance(change, dict) else change.old_value
            new_v = change.get("new_value") if isinstance(change, dict) else change.new_value
            reason = change.get("reason") if isinstance(change, dict) else change.reason
            lines.append(f"- {path}: {old_v!r} -> {new_v!r} ({reason})")
        return "\n".join(lines)

    @staticmethod
    def _dict_view_text(block: dict) -> str:
        base = block.get("base", "")
        quote = block.get("quote", "")
        name = block.get("name", "")
        asset = block.get("asset", "")
        lines = [f"# {base} / {quote} — {name}", f"`{asset}`"]
        for section in block.get("sections", []):
            title = section.get("title", "") if isinstance(section, dict) else section.title
            lines.append(f"\n## {title}")
            fields = section.get("fields", []) if isinstance(section, dict) else section.fields
            for f in fields:
                f_path = f.get("path") if isinstance(f, dict) else f.path
                f_val = f.get("value") if isinstance(f, dict) else f.value
                lines.append(f"- {f_path}: {f_val!r}")
        return "\n".join(lines)
