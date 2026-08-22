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

    def _collect_wholesale_validation_errors(
            self,
            patched_config: dict,
            applied_changes: List[ConfigChange],
            errors: List[str],
    ) -> None:
        try:
            TRADING_CONFIG_ADAPTER.validate_python(patched_config)
        except ValidationError as validation_error:
            for pydantic_error in validation_error.errors():
                error_loc = pydantic_error.get("loc", ())
                error_message = pydantic_error.get("msg", "invalid value")
                error_dot_path = self._loc_to_dot_path(error_loc, patched_config)

                matched_change_path = self._find_change_for_error_path(error_dot_path, applied_changes)
                if matched_change_path:
                    errors.append(
                        f"Field '{matched_change_path}' value {pydantic_error.get('input')!r} "
                        f"violates constraint: {error_message} (loc: {error_dot_path})"
                    )
                else:
                    error_loc_str = ".".join(str(part) for part in error_loc) if error_loc else "root"
                    errors.append(f"Field '{error_loc_str}' ({error_dot_path}): {error_message}")

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
            self._collect_wholesale_validation_errors(patched_config, applied_changes, errors)

        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)

    def _asset_error_dot_path(self, error_loc: Tuple[Any, ...], patched_config: dict) -> str:
        asset_index = error_loc[1] if len(error_loc) > 1 and isinstance(error_loc[1], int) else None
        if asset_index is None:
            return ".".join(str(part) for part in error_loc)

        assets = patched_config.get("assets", [])
        if 0 <= asset_index < len(assets):
            asset_symbol = ConfigurationSchema.asset_symbol(assets[asset_index])
        else:
            asset_symbol = str(asset_index)

        if len(error_loc) == 2:
            return f"assets.{asset_symbol}"
        if len(error_loc) == 3:
            return f"assets.{asset_symbol}.{error_loc[2]}"
        if len(error_loc) >= 4 and error_loc[2] == "guard_config":
            return f"assets.{asset_symbol}.guard_config.{error_loc[3]}"
        if len(error_loc) >= 4 and error_loc[2] == "consensus":
            return f"assets.{asset_symbol}.consensus.{error_loc[3]}"
        if len(error_loc) >= 4 and error_loc[2] == "strategies":
            strategy_index = error_loc[3] if isinstance(error_loc[3], int) else None
            if strategy_index is not None:
                strategy_entries = assets[asset_index].get("strategies", [])
                strategy_entry = strategy_entries[strategy_index] if strategy_index < len(strategy_entries) else {}
                strategy_name = strategy_entry.get("name", str(strategy_index))
                if len(error_loc) >= 5:
                    return f"assets.{asset_symbol}.strategies.{strategy_name}.{error_loc[4]}"
                return f"assets.{asset_symbol}.strategies.{strategy_name}"

        remaining_parts = ".".join(str(part) for part in error_loc[2:])
        return f"assets.{asset_symbol}.{remaining_parts}"

    def _loc_to_dot_path(self, error_loc: Tuple[Any, ...], patched_config: dict) -> str:
        if not error_loc:
            return ""
        if error_loc[0] != "assets":
            return ".".join(str(part) for part in error_loc)
        try:
            return self._asset_error_dot_path(error_loc, patched_config)
        except Exception:
            return ".".join(str(part) for part in error_loc)

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
