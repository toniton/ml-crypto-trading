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
    ConfigurationViewBlock,
    FieldRow,
    MarkdownBlock,
    SectionCard,
    SignalWindow,
    StatCard,
    StrategyCard,
    UIBlock,
    ValidationResult,
)
from src.agent.configuration.schema import (
    ConfigField,
    ConfigurationSchema,
    TRADING_CONFIG_ADAPTER,
)
from src.configuration.trading_config import TradingConfig
from src.logging.agent_logging_mixin import AgentLoggingMixin
from src.vcs.application.service import VCSService
from src.vcs.domain.exceptions import VcsError


class ConfigurationService(AgentLoggingMixin):
    def __init__(self, config_filepath: str, vcs: Optional["VCSService"] = None):
        self._config_filepath = config_filepath
        self._schema = ConfigurationSchema()
        self._vcs = vcs

    @property
    def config_filepath(self) -> str:
        return self._config_filepath

    def load_raw_config(self) -> dict:
        if self._vcs is not None:
            try:
                return self._vcs.checkout("HEAD")
            except VcsError:
                self.agent_logger.warning(
                    "No committed configuration at HEAD; falling back to on-disk file %s",
                    self._config_filepath,
                )
        with open(self._config_filepath, "r", encoding="utf-8") as stream:
            return yaml.safe_load(stream) or {}

    def get_field_catalog(self) -> List[ConfigField]:
        return self._schema.build_field_catalog(self.load_raw_config())

    def render_catalog(self) -> str:
        return self._schema.render_catalog(self.get_field_catalog())

    def render_configuration_view(self, target_asset: Optional[str] = None) -> str:
        fields = self.get_field_catalog()
        if target_asset:
            prefix = f"assets.{target_asset}."
            fields = [field for field in fields if field.path.startswith(prefix)]
        return self._schema.render_catalog(fields)

    @staticmethod
    def _parse_enum_values(field: ConfigField) -> list[str]:
        for constraint in field.constraints:
            if constraint.startswith("value in {"):
                inner = constraint[len("value in {") : -1]
                return [item.strip() for item in inner.split(",") if item.strip()]
        return []

    @staticmethod
    def _section_for_field(field: ConfigField) -> str:
        """Returns a section key for a field based on its catalog path."""
        path = field.path
        if ".consensus." in path or path.endswith(".consensus"):
            return "consensus"
        if ".guard_config." in path or path.endswith(".guard_config"):
            return "drawdown_guard"
        if ".strategies." in path or path.endswith(".strategies"):
            return "strategies"
        if path.endswith(".base_ticker_symbol") or path.endswith(".quote_ticker_symbol"):
            return "identity"
        if path.endswith(".separator") or path.endswith(".exchange"):
            return "identity"
        if path.endswith(".quantity_decimals") or path.endswith(".quote_decimals"):
            return "identity"
        if path.endswith(".name"):
            return "identity"
        if path.endswith(".candles_timeframe") or path.endswith(".schedule"):
            return "market_feed"
        if path.endswith(".min_quantity"):
            return "trade_sizing"
        return "other"

    _SECTION_DEFINITIONS: dict[str, tuple[str, str, str]] = {
        "identity": ("Asset identity", "Fixed pair metadata. Locked at the exchange level — these values cannot be changed at runtime.", "assets.{asset}"),
        "market_feed": ("Market feed", "How often candles stream in and how frequently the strategy loop ticks.", "assets.{asset}"),
        "consensus": ("Consensus thresholds", "Weighted vote total required before the bot fires a signal. Strategies vote; consensus decides.", "assets.{asset}.consensus"),
        "drawdown_guard": ("Drawdown guard", "Circuit breaker. Halts trading when losses breach the tolerated drawdown window.", "assets.{asset}.guard_config"),
        "trade_sizing": ("Trade sizing", "Minimum executable order size on the exchange.", "assets.{asset}"),
    }

    _SCHEDULE_LABELS: dict = {0: "second", 1: "minute", 2: "hour", 3: "day", 4: "week", 5: "month"}

    _HIDDEN_VIEW_FIELD_NAMES: frozenset[str] = frozenset({"quote_decimals", "quantity_decimals"})

    def build_configuration_view(self, target_asset: str) -> ConfigurationViewBlock:
        fields = self.get_field_catalog()
        prefix = f"assets.{target_asset}."
        asset_fields = [
            field for field in fields
            if field.path.startswith(prefix) and self._is_visible_in_view(field)
        ]

        non_strategy_sections = [
            self._section_for_field(field) for field in asset_fields
            if self._section_for_field(field) != "strategies"
        ]
        field_rows = [
            self._to_field_row(field)
            for field in asset_fields
            if self._section_for_field(field) != "strategies"
        ]

        by_section: dict[str, list[FieldRow]] = {}
        for section_key, row in zip(non_strategy_sections, field_rows):
            by_section.setdefault(section_key, []).append(row)

        sections: list[SectionCard] = []
        for key, (title, description, path_template) in self._SECTION_DEFINITIONS.items():
            rows = by_section.get(key)
            if not rows:
                continue
            rows.sort(key=lambda row: row.path)
            sections.append(
                SectionCard(
                    title=title,
                    path=path_template.format(asset=target_asset),
                    description=description,
                    fields=rows,
                )
            )

        strategies = self._build_strategy_cards(asset_fields, target_asset)

        raw_config = self.load_raw_config()
        asset_entry = ConfigurationSchema.find_asset_entry(raw_config, target_asset)
        return self._assemble_view(asset_entry, sections, strategies, field_rows, target_asset)

    @staticmethod
    def _is_visible_in_view(field: ConfigField) -> bool:
        return field.path.rsplit(".", 1)[-1] not in ConfigurationService._HIDDEN_VIEW_FIELD_NAMES

    def _to_field_row(self, field: ConfigField) -> FieldRow:
        return FieldRow(
            name=field.path.rsplit(".", 1)[-1],
            path=field.path,
            value=field.value,
            type=field.type,
            mutable=field.mutable,
            description=field.description,
            constraints=list(field.constraints),
            enum_values=self._parse_enum_values(field),
        )

    def _build_strategy_cards(self, asset_fields: list[ConfigField], asset_symbol: str) -> list[StrategyCard]:
        grouping: dict[str, dict[str, ConfigField]] = {}
        for field in asset_fields:
            if self._section_for_field(field) != "strategies":
                continue
            parts = field.path.split(".")
            strategy_name, field_name = parts[3], parts[4]
            grouping.setdefault(strategy_name, {})[field_name] = field

        cards: list[StrategyCard] = []
        for name, components in grouping.items():
            def value(field_name: str) -> Optional[Any]:
                field = components.get(field_name)
                return field.value if field is not None else None

            cards.append(
                StrategyCard(
                    name=name,
                    path=f"assets.{asset_symbol}.strategies.{name}",
                    action=str(value("action")) if value("action") is not None else "",
                    kind=str(value("type")) if value("type") is not None else "",
                    enabled=value("enabled") if value("enabled") is not None else None,
                    expression=value("expression") if value("expression") is not None else None,
                    class_name=value("class_name") if value("class_name") is not None else None,
                )
            )
        return sorted(cards, key=lambda card: card.name)

    def _assemble_view(
            self,
            asset_entry: Optional[dict],
            sections: list[SectionCard],
            strategies: list[StrategyCard],
            field_rows: list[FieldRow],
            asset_symbol: str,
    ) -> ConfigurationViewBlock:
        stats = self._build_stat_cards(asset_entry)
        signal_window = self._build_signal_window(asset_entry)
        editable_count = sum(1 for row in field_rows if row.mutable)
        return ConfigurationViewBlock(
            asset=asset_symbol,
            name=asset_entry.get("name", asset_symbol) if asset_entry else asset_symbol,
            base=asset_entry.get("base_ticker_symbol", "") if asset_entry else "",
            quote=asset_entry.get("quote_ticker_symbol", "") if asset_entry else "",
            stats=stats,
            sections=sections,
            strategies=strategies,
            signal_window=signal_window,
            editable_count=editable_count,
            field_count=len(field_rows),
        )

    def _build_stat_cards(self, asset_entry: Optional[dict]) -> list[StatCard]:
        if not asset_entry:
            return []
        consensus = asset_entry.get("consensus") or {}
        cards = [
            StatCard(label="Exchange", value=str(asset_entry.get("exchange", "")).replace("_DOT_", ".")),
            StatCard(label="Timeframe", value=str(asset_entry.get("candles_timeframe", ""))),
        ]
        if "buy" in consensus:
            cards.append(StatCard(label="Buy ≥", value=str(consensus["buy"]), tint="buy"))
        if "sell" in consensus:
            cards.append(StatCard(label="Sell ≥", value=str(consensus["sell"]), tint="sell"))
        cards.append(StatCard(label="Strategies", value=str(len(asset_entry.get("strategies") or []))))
        return cards

    def _build_signal_window(self, asset_entry: Optional[dict]) -> Optional[SignalWindow]:
        if not asset_entry:
            return None
        consensus = asset_entry.get("consensus") or {}
        if "buy" not in consensus or "sell" not in consensus:
            return None
        return SignalWindow(min=0.05, sell=consensus["sell"], buy=consensus["buy"], max=10.0)

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

    def apply_proposal_to_vcs(
            self,
            proposal: ConfigurationProposal,
            author: str = "user",
            ref: str = "HEAD",
    ) -> Tuple[Any, List[str]]:
        if self._vcs is None:
            raise RuntimeError("ConfigurationService has no VCS backend configured.")

        patched, warnings = self.apply_proposal(proposal)
        validated_config = TradingConfig.model_validate(patched)
        commit = self._vcs.commit(
            validated_config,
            author=author,
            message=proposal.summary,
            ref=ref,
        )
        return commit, warnings

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
