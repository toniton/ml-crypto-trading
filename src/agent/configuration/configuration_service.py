from __future__ import annotations

import copy
from typing import Any, List, Optional, Tuple

import yaml
from pydantic import ValidationError

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
from src.agent.configuration.schema import (
    ConfigField,
    ConfigurationSchema,
    TRADING_CONFIG_ADAPTER,
)
from src.configuration.trading_config import TradingConfig


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

    def _apply_changes_to_patch(
            self,
            raw_config: dict,
            changes: List[ConfigChange],
            catalog_by_path: dict,
            errors: List[str],
            warnings: List[str],
    ) -> Tuple[dict, List[ConfigChange]]:
        patched_config = copy.deepcopy(raw_config)
        applied_changes: List[ConfigChange] = []

        for change in changes:
            field = catalog_by_path.get(change.path)
            if field is None:
                errors.append(f"Unknown configuration path: {change.path}")
                continue
            if not field.mutable:
                errors.append(f"Field '{change.path}' is locked and cannot be changed.")
                continue

            current_value = ConfigurationSchema.get_value(raw_config, change.path)
            if current_value != change.old_value:
                warnings.append(
                    f"Field '{change.path}' current value ({current_value!r}) differs from the "
                    f"proposed old_value ({change.old_value!r}); the patch has been rebased."
                )

            if not ConfigurationSchema.set_value(patched_config, change.path, change.new_value):
                errors.append(f"Failed to set value for '{change.path}'")
                continue

            applied_changes.append(change)

        return patched_config, applied_changes

    def _find_change_for_error_path(self, error_dot_path: str, applied_changes: List[ConfigChange]) -> Optional[str]:
        for change in applied_changes:
            if (
                    error_dot_path == change.path
                    or error_dot_path.startswith(change.path + ".")
                    or change.path.startswith(error_dot_path + ".")
            ):
                return change.path
        return None

    def _preexisting_error_keys(self, raw_config: dict) -> set:
        try:
            TRADING_CONFIG_ADAPTER.validate_python(raw_config)
        except ValidationError as validation_error:
            return {
                (tuple(pydantic_error.get("loc", ())), pydantic_error.get("type"))
                for pydantic_error in validation_error.errors()
            }
        return set()

    @staticmethod
    def _reported_error_value(pydantic_error: dict, patched_config: dict, change_path: str) -> Any:
        error_input = pydantic_error.get("input")
        if isinstance(error_input, (dict, list)):
            return ConfigurationSchema.get_value(patched_config, change_path)
        return error_input

    def _collect_wholesale_validation_errors(
            self,
            raw_config: dict,
            patched_config: dict,
            applied_changes: List[ConfigChange],
            errors: List[str],
            warnings: List[str],
    ) -> Optional[TradingConfig]:
        try:
            return TRADING_CONFIG_ADAPTER.validate_python(patched_config)
        except ValidationError as validation_error:
            preexisting_error_keys = self._preexisting_error_keys(raw_config)

            for pydantic_error in validation_error.errors():
                error_loc = tuple(pydantic_error.get("loc", ()))
                error_message = pydantic_error.get("msg", "invalid value")
                error_dot_path = self._loc_to_dot_path(error_loc, patched_config)
                matched_change_path = self._find_change_for_error_path(error_dot_path, applied_changes)

                if matched_change_path:
                    reported_value = self._reported_error_value(
                        pydantic_error, patched_config, matched_change_path
                    )
                    location_hint = "" if error_dot_path == matched_change_path else f" (at {error_dot_path})"
                    errors.append(
                        f"Field '{matched_change_path}' value {reported_value!r} "
                        f"violates constraint: {error_message}{location_hint}"
                    )
                elif (error_loc, pydantic_error.get("type")) in preexisting_error_keys:
                    warnings.append(
                        f"Field '{error_dot_path}' was already invalid before this proposal "
                        f"({error_message}); these changes leave it untouched."
                    )
                else:
                    errors.append(f"Field '{error_dot_path}': {error_message}")

            return None

    @staticmethod
    def _normalize_change_values(validated_config: TradingConfig, changes: List[ConfigChange]) -> None:
        normalized_config = TRADING_CONFIG_ADAPTER.dump_python(validated_config, mode="json")
        for change in changes:
            normalized_value = ConfigurationSchema.get_value(normalized_config, change.path)
            if normalized_value is not None:
                change.new_value = normalized_value

    def validate_proposal(self, proposal: ConfigurationProposal) -> ValidationResult:
        if not proposal.changes:
            return ValidationResult.failed(["Proposal contains no changes."])

        raw_config = self.load_raw_config()
        errors: List[str] = []
        warnings: List[str] = []

        catalog_by_path = {field.path: field for field in self.get_field_catalog()}

        patched_config, applied_changes = self._apply_changes_to_patch(
            raw_config, proposal.changes, catalog_by_path, errors, warnings
        )

        if applied_changes:
            validated_config = self._collect_wholesale_validation_errors(
                raw_config, patched_config, applied_changes, errors, warnings
            )
            if validated_config is not None:
                self._normalize_change_values(validated_config, applied_changes)
            elif not errors:
                warnings.append(
                    "Proposed values could not be type-normalized because the configuration has "
                    "pre-existing validation errors; they will be written exactly as proposed."
                )

        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)

    def _loc_to_dot_path(self, error_loc: Tuple[Any, ...], patched_config: dict) -> str:
        path_parts: List[str] = []
        current_node: Any = patched_config

        for loc_part in error_loc:
            if isinstance(loc_part, int) and isinstance(current_node, list):
                list_entry = current_node[loc_part] if 0 <= loc_part < len(current_node) else None
                entry_key = ConfigurationSchema.entry_key(list_entry) if isinstance(list_entry, dict) else ""
                path_parts.append(entry_key or str(loc_part))
                current_node = list_entry
                continue

            path_parts.append(str(loc_part))
            current_node = current_node.get(loc_part) if isinstance(current_node, dict) else None

        return ".".join(path_parts)

    def apply_proposal(self, proposal: ConfigurationProposal) -> Tuple[dict, List[str]]:
        raw_config = self.load_raw_config()
        patched_config = copy.deepcopy(raw_config)
        warnings: List[str] = []

        for change in proposal.changes:
            if ConfigurationSchema.get_value(raw_config, change.path) != change.old_value:
                warnings.append(
                    f"Field '{change.path}' was rebased from {change.old_value!r} to its current value."
                )
            ConfigurationSchema.set_value(patched_config, change.path, change.new_value)

        try:
            validated_config = TRADING_CONFIG_ADAPTER.validate_python(patched_config)
        except ValidationError as validation_error:
            warnings.append(
                f"Applied configuration does not validate "
                f"({validation_error.error_count()} error(s)); call validate_proposal first."
            )
            return patched_config, warnings

        self._normalize_change_values(validated_config, proposal.changes)
        for change in proposal.changes:
            ConfigurationSchema.set_value(patched_config, change.path, change.new_value)

        return patched_config, warnings

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
            errors: Optional[List[str]] = None,
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
        if errors:
            blocks.append(
                MarkdownBlock.from_text(
                    "This proposal was rejected because it fails validation:\n"
                    + "\n".join(f"- {error}" for error in errors)
                )
            )
        else:
            blocks.append(ApprovalBlock.build())
        return ConfigurationPresentation(blocks=blocks)
