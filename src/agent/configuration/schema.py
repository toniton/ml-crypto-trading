from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, Field, TypeAdapter

from src.configuration.trading_config import TradingConfig


class ConfigField(BaseModel):
    path: str = Field(description="Dot-separated path that addresses this field in the config.")
    value: Any = Field(description="Current value of the field.")
    description: str = Field(description="Plain-language explanation of the field's purpose.")
    type: str = Field(description="Semantic type: decimal, int, bool, enum, or string.")
    mutable: bool = Field(description="Whether the field may be changed without a restart.")
    constraints: list[str] = Field(
        default_factory=list,
        description="Machine-checkable constraints, e.g. '0.50 <= value <= 0.95'.",
    )


TRADING_CONFIG_ADAPTER: TypeAdapter[TradingConfig] = TypeAdapter(TradingConfig)
_TRADING_CONFIG_SCHEMA_CACHE: dict[str, Any] | None = None

_RANGE_CONSTRAINT_PATTERN = re.compile(
    r"^(?P<lo>[+-]?\d+(?:\.\d+)?)\s*<=\s*value\s*<=\s*(?P<hi>[+-]?\d+(?:\.\d+)?)$"
)
_COMPARISON_CONSTRAINT_PATTERN = re.compile(
    r"^value\s*(?P<op><=|>=|<|>)\s*(?P<num>[+-]?\d+(?:\.\d+)?)$"
)
_SET_CONSTRAINT_PATTERN = re.compile(r"^value\s+in\s+\{(.*)\}$")
_COMPARISON_OPERATORS = {
    "<": lambda left, right: left < right,
    "<=": lambda left, right: left <= right,
    ">": lambda left, right: left > right,
    ">=": lambda left, right: left >= right,
}


def get_trading_config_json_schema() -> dict[str, Any]:
    global _TRADING_CONFIG_SCHEMA_CACHE
    if _TRADING_CONFIG_SCHEMA_CACHE is None:
        _TRADING_CONFIG_SCHEMA_CACHE = TRADING_CONFIG_ADAPTER.json_schema()
    return _TRADING_CONFIG_SCHEMA_CACHE


def _unwrap_optional(field_schema: dict[str, Any]) -> dict[str, Any]:
    if "anyOf" in field_schema:
        non_null_branch = None
        for branch in field_schema["anyOf"]:
            if branch.get("type") != "null":
                non_null_branch = branch
                break
        if non_null_branch is not None:
            merged_schema: dict[str, Any] = dict(non_null_branch)
            for key, value in field_schema.items():
                if key not in ("anyOf", "default") and key not in merged_schema:
                    merged_schema[key] = value
            return merged_schema
    return field_schema


def _resolve_ref(field_schema: dict[str, Any], schema_defs: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in field_schema:
        ref_name = field_schema["$ref"].split("/")[-1]
        referenced_schema = schema_defs.get(ref_name, {})
        merged_schema: dict[str, Any] = dict(referenced_schema)
        for key, value in field_schema.items():
            if key != "$ref" and key not in merged_schema:
                merged_schema[key] = value
        return merged_schema
    return field_schema


def _effective_schema(field_schema: dict[str, Any], schema_defs: dict[str, Any]) -> dict[str, Any]:
    unwrapped_schema = _unwrap_optional(field_schema)
    if "$ref" in unwrapped_schema:
        return _resolve_ref(unwrapped_schema, schema_defs)
    return unwrapped_schema


def _derive_type(field_schema: dict[str, Any], schema_defs: dict[str, Any]) -> str:
    effective_schema = _effective_schema(field_schema, schema_defs)
    if "enum" in effective_schema:
        return "enum"
    json_type = effective_schema.get("type")
    if json_type == "number":
        return "decimal"
    if json_type == "integer":
        return "int"
    if json_type == "string":
        return "string"
    if json_type == "boolean":
        return "bool"
    return "string"


def _derive_constraints(field_schema: dict[str, Any], schema_defs: dict[str, Any]) -> list[str]:
    effective_schema = _effective_schema(field_schema, schema_defs)
    constraints: list[str] = []

    if "enum" in effective_schema:
        allowed_values = ", ".join(str(value) for value in effective_schema["enum"])
        constraints.append(f"value in {{{allowed_values}}}")
        return constraints

    if "exclusiveMinimum" in effective_schema:
        constraints.append(f"value > {effective_schema['exclusiveMinimum']}")
    elif "minimum" in effective_schema:
        constraints.append(f"value >= {effective_schema['minimum']}")

    if "exclusiveMaximum" in effective_schema:
        constraints.append(f"value < {effective_schema['exclusiveMaximum']}")
    elif "maximum" in effective_schema:
        constraints.append(f"value <= {effective_schema['maximum']}")

    if "minLength" in effective_schema:
        if effective_schema["minLength"] == 1:
            constraints.append("value is a non-empty string")
        else:
            constraints.append(f"value length >= {effective_schema['minLength']}")

    return constraints


def _derive_mutable(field_schema: dict[str, Any], schema_defs: dict[str, Any]) -> bool:
    if "mutable" in field_schema:
        return bool(field_schema["mutable"])
    unwrapped_schema = _unwrap_optional(field_schema)
    if "mutable" in unwrapped_schema:
        return bool(unwrapped_schema["mutable"])
    return False


def _derive_description(field_schema: dict[str, Any], schema_defs: dict[str, Any]) -> str:
    unwrapped_schema = _unwrap_optional(field_schema)
    if "description" in unwrapped_schema:
        return str(unwrapped_schema["description"])
    if "description" in field_schema:
        return str(field_schema["description"])
    if "$ref" in unwrapped_schema:
        referenced_schema = _resolve_ref(unwrapped_schema, schema_defs)
        if "description" in referenced_schema:
            return str(referenced_schema["description"])
    return ""


class ConfigurationSchema:
    @staticmethod
    def asset_symbol(asset_entry: dict) -> str:
        return f"{asset_entry.get('base_ticker_symbol', '?')}_{asset_entry.get('quote_ticker_symbol', '?')}"

    @staticmethod
    def find_asset_entry(raw_config: dict, symbol: str) -> Optional[dict]:
        for asset_entry in raw_config.get("assets", []):
            if ConfigurationSchema.asset_symbol(asset_entry) == symbol:
                return asset_entry
        return None

    @staticmethod
    def find_asset_strategy_entry(asset_entry: dict, strategy_name: str) -> Optional[dict]:
        for strategy_entry in asset_entry.get("strategies", []):
            if strategy_entry.get("name") == strategy_name:
                return strategy_entry
        return None

    @staticmethod
    def _descend_path(root: dict, path_parts: list[str]) -> Any:
        current_value: Any = root
        for part in path_parts:
            if not isinstance(current_value, dict) or part not in current_value:
                return None
            current_value = current_value[part]
        return current_value

    @staticmethod
    def get_value(raw_config: dict, path: str) -> Any:
        path_parts = path.split(".")
        if path_parts[0] == "assets" and len(path_parts) >= 3:
            asset_entry = ConfigurationSchema.find_asset_entry(raw_config, path_parts[1])
            if asset_entry is None:
                return None
            if path_parts[2] == "strategies" and len(path_parts) >= 5:
                strategy_entry = ConfigurationSchema.find_asset_strategy_entry(asset_entry, path_parts[3])
                if strategy_entry is None:
                    return None
                return ConfigurationSchema._descend_path(strategy_entry, path_parts[4:])
            return ConfigurationSchema._descend_path(asset_entry, path_parts[2:])
        return ConfigurationSchema._descend_path(raw_config, path_parts)

    @staticmethod
    def set_value(raw_config: dict, path: str, value: Any) -> bool:
        path_parts = path.split(".")
        if path_parts[0] == "assets" and len(path_parts) >= 3:
            asset_entry = ConfigurationSchema.find_asset_entry(raw_config, path_parts[1])
            if asset_entry is None:
                return False
            if path_parts[2] == "strategies" and len(path_parts) >= 5:
                strategy_entry = ConfigurationSchema.find_asset_strategy_entry(asset_entry, path_parts[3])
                if strategy_entry is None:
                    return False
                return ConfigurationSchema._set_descend(strategy_entry, path_parts[4:], value)
            return ConfigurationSchema._set_descend(asset_entry, path_parts[2:], value)
        return ConfigurationSchema._set_descend(raw_config, path_parts, value)

    @staticmethod
    def _set_descend(root: dict, path_parts: list[str], value: Any) -> bool:
        target = root
        for part in path_parts[:-1]:
            if not isinstance(target, dict) or part not in target:
                return False
            target = target[part]
        last_part = path_parts[-1]
        if not isinstance(target, dict) or last_part not in target:
            return False
        target[last_part] = value
        return True

    def _build_config_field(self, raw_config: dict, path: str, field_schema: dict, schema_defs: dict) -> ConfigField:
        return ConfigField(
            path=path,
            value=self.get_value(raw_config, path),
            description=_derive_description(field_schema, schema_defs),
            type=_derive_type(field_schema, schema_defs),
            mutable=_derive_mutable(field_schema, schema_defs),
            constraints=_derive_constraints(field_schema, schema_defs),
        )

    def _build_top_level_fields(self, raw_config: dict, schema_properties: dict, schema_defs: dict) -> list[ConfigField]:
        fields: list[ConfigField] = []
        for field_name, field_schema in schema_properties.items():
            if field_name == "assets":
                continue
            fields.append(self._build_config_field(raw_config, field_name, field_schema, schema_defs))
        return fields

    def _build_strategy_fields(
            self,
            raw_config: dict,
            asset_symbol: str,
            field_name: str,
            strategy_entries: list,
            strategy_schema: dict,
            schema_defs: dict,
    ) -> list[ConfigField]:
        fields: list[ConfigField] = []
        for strategy_entry in strategy_entries or []:
            if not isinstance(strategy_entry, dict):
                continue
            strategy_name = strategy_entry.get("name")
            if not strategy_name:
                continue
            for strategy_field_name, strategy_field_schema in strategy_schema.get("properties", {}).items():
                path = f"assets.{asset_symbol}.{field_name}.{strategy_name}.{strategy_field_name}"
                fields.append(self._build_config_field(raw_config, path, strategy_field_schema, schema_defs))
        return fields

    def _build_nested_object_fields(
            self,
            raw_config: dict,
            asset_symbol: str,
            field_name: str,
            nested_properties: dict,
            schema_defs: dict,
    ) -> list[ConfigField]:
        fields: list[ConfigField] = []
        for nested_field_name, nested_field_schema in nested_properties.items():
            path = f"assets.{asset_symbol}.{field_name}.{nested_field_name}"
            fields.append(self._build_config_field(raw_config, path, nested_field_schema, schema_defs))
        return fields

    def _build_asset_fields(self, raw_config: dict, asset_properties: dict, schema_defs: dict) -> list[ConfigField]:
        fields: list[ConfigField] = []
        for asset_entry in raw_config.get("assets", []):
            asset_symbol = self.asset_symbol(asset_entry)
            for field_name, field_schema in asset_properties.items():
                effective_schema = _effective_schema(field_schema, schema_defs)

                if effective_schema.get("type") == "array":
                    item_schema = _effective_schema(effective_schema.get("items", {}), schema_defs)
                    fields.extend(
                        self._build_strategy_fields(
                            raw_config,
                            asset_symbol,
                            field_name,
                            asset_entry.get(field_name, []),
                            item_schema,
                            schema_defs,
                        )
                    )
                    continue

                if "properties" in effective_schema:
                    fields.extend(
                        self._build_nested_object_fields(
                            raw_config,
                            asset_symbol,
                            field_name,
                            effective_schema["properties"],
                            schema_defs,
                        )
                    )
                    continue

                path = f"assets.{asset_symbol}.{field_name}"
                fields.append(self._build_config_field(raw_config, path, field_schema, schema_defs))
        return fields

    def build_field_catalog(self, raw_config: dict) -> list[ConfigField]:
        trading_config_schema = get_trading_config_json_schema()
        schema_defs = trading_config_schema.get("$defs", {})
        schema_properties = trading_config_schema.get("properties", {})

        fields = self._build_top_level_fields(raw_config, schema_properties, schema_defs)

        asset_schema = _effective_schema(schema_properties.get("assets", {}).get("items", {}), schema_defs)
        asset_properties = asset_schema.get("properties", {})
        fields.extend(self._build_asset_fields(raw_config, asset_properties, schema_defs))

        return fields

    def render_catalog(self, fields: list[ConfigField]) -> str:
        lines = ["Current configuration fields available to change:"]
        for field in sorted(fields, key=lambda f: f.path):
            mutability_label = "editable" if field.mutable else "locked"
            lines.append(
                f"- {field.path} [{mutability_label}, {field.type}] = {field.value!r} "
                f"-- {field.description}"
            )
            for constraint in field.constraints:
                lines.append(f"    constraint: {constraint}")
        return "\n".join(lines)

    @staticmethod
    def _as_number(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def check_constraint(value: Any, constraint: str) -> bool:
        stripped_constraint = constraint.strip()

        range_match = _RANGE_CONSTRAINT_PATTERN.match(stripped_constraint)
        if range_match:
            number = ConfigurationSchema._as_number(value)
            if number is not None:
                return float(range_match.group("lo")) <= number <= float(range_match.group("hi"))

        comparison_match = _COMPARISON_CONSTRAINT_PATTERN.match(stripped_constraint)
        if comparison_match:
            number = ConfigurationSchema._as_number(value)
            if number is not None:
                operator = _COMPARISON_OPERATORS[comparison_match.group("op")]
                return operator(number, float(comparison_match.group("num")))

        set_match = _SET_CONSTRAINT_PATTERN.match(stripped_constraint)
        if set_match:
            allowed_values = {item.strip() for item in set_match.group(1).split(",")}
            return str(value) in allowed_values

        if stripped_constraint == "value is a non-empty string":
            return isinstance(value, str) and len(value.strip()) > 0

        return True
