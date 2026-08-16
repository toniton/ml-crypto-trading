from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

import yaml

from src.agent.configuration.models import (
    ApprovalBlock,
    ConfigChange,
    ConfigurationDiffBlock,
    ConfigurationPresentation,
    ConfigurationProposal,
    MarkdownBlock,
    UIBlock,
    ValidationResult,
)
from src.agent.configuration.schema import ConfigField, ConfigurationSchema

_TYPE_CONVERTERS: Dict[str, Any] = {
    "int": int,
    "decimal": float,
    "enum": str,
    "string": str,
}


class ConfigurationService:
    def __init__(self, config_filepath: str):
        self._config_filepath = config_filepath
        self._schema = ConfigurationSchema()

    @property
    def config_filepath(self) -> str:
        return self._config_filepath

    def load_raw_config(self) -> dict:
        with open(self._config_filepath, "r", encoding="utf-8") as stream:
            return yaml.safe_load(stream) or {}

    def get_field_catalog(self) -> List[ConfigField]:
        return self._schema.build_field_catalog(self.load_raw_config())

    def render_catalog(self) -> str:
        return self._schema.render_catalog(self.get_field_catalog())

    def current_value(self, path: str) -> Any:
        return ConfigurationSchema.get_value(self.load_raw_config(), path)

    def validate_proposal(self, proposal: ConfigurationProposal) -> ValidationResult:
        if not proposal.changes:
            return ValidationResult.failed(["Proposal contains no changes."])

        raw_config = self.load_raw_config()
        errors: List[str] = []
        warnings: List[str] = []

        for change in proposal.changes:
            field = self._find_field(change.path)
            if field is None:
                errors.append(f"Unknown configuration path: {change.path}")
                continue
            if not field.mutable:
                errors.append(f"Field '{change.path}' is locked and cannot be changed.")
                continue

            current = ConfigurationSchema.get_value(raw_config, change.path)
            if current != change.old_value:
                warnings.append(
                    f"Field '{change.path}' current value ({current!r}) differs from the "
                    f"proposed old_value ({change.old_value!r}); the patch has been rebased."
                )

            if not self._try_coerce(change):
                errors.append(
                    f"Field '{change.path}' expects {field.type}, cannot accept {change.new_value!r}."
                )
                continue

            coerced = change.new_value
            for constraint in field.constraints:
                if not ConfigurationSchema.check_constraint(coerced, constraint):
                    errors.append(
                        f"Field '{change.path}' value {coerced!r} violates constraint: {constraint}"
                    )
                    break

        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)

    def apply_proposal(self, proposal: ConfigurationProposal) -> Tuple[dict, List[str]]:
        raw_config = copy.deepcopy(self.load_raw_config())
        warnings: List[str] = []
        for change in proposal.changes:
            if ConfigurationSchema.get_value(raw_config, change.path) != change.old_value:
                warnings.append(
                    f"Field '{change.path}' was rebased from {change.old_value!r} to its current value."
                )
            ConfigurationSchema.set_value(raw_config, change.path, change.new_value)
        return raw_config, warnings

    def render_proposed_diff(self, proposal: ConfigurationProposal, warnings: Optional[List[str]] = None) -> str:
        lines = [proposal.summary]
        for change in proposal.changes:
            lines.append(f"- {change.path}: {change.old_value!r} -> {change.new_value!r}")
            lines.append(f"    reason: {change.reason}")
        if proposal.risks:
            lines.append("Risks:")
            lines.extend(f"  - {risk}" for risk in proposal.risks)
        if proposal.expected_effect:
            lines.append(f"Expected effect: {proposal.expected_effect}")
        if warnings:
            lines.append("Warnings:")
            lines.extend(f"  - {warning}" for warning in warnings)
        return "\n".join(lines)

    def build_presentation(
            self,
            proposal: ConfigurationProposal,
            warnings: Optional[List[str]] = None,
    ) -> ConfigurationPresentation:
        blocks: list[UIBlock] = [MarkdownBlock.from_text(proposal.summary)]
        if proposal.changes:
            blocks.append(
                ConfigurationDiffBlock(
                    prefix="Proposed changes",
                    changes=list(proposal.changes),
                )
            )
        if proposal.risks:
            blocks.append(MarkdownBlock.from_text("Risks:\n" + "\n".join(f"- {r}" for r in proposal.risks)))
        if proposal.expected_effect:
            blocks.append(MarkdownBlock.from_text(f"Expected effect: {proposal.expected_effect}"))
        if warnings:
            blocks.append(MarkdownBlock.from_text("Warnings:\n" + "\n".join(f"- {w}" for w in warnings)))
        blocks.append(ApprovalBlock.build())
        return ConfigurationPresentation(blocks=blocks)

    def _find_field(self, path: str) -> ConfigField | None:
        for field in self.get_field_catalog():
            if field.path == path:
                return field
        return None

    def _try_coerce(self, change: ConfigChange) -> bool:
        field = self._find_field(change.path)
        if field is None:
            return False
        converter = _TYPE_CONVERTERS.get(field.type)
        if converter is None:
            return True
        try:
            change.new_value = converter(change.new_value)
            return True
        except (TypeError, ValueError):
            return False
