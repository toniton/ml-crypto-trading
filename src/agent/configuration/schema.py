from __future__ import annotations

import re
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Optional

from pydantic import BaseModel, Field


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


@dataclass(frozen=True)
class ConfigFieldSpec:
    """A static (non-validated) field definition shared by all assets / sections."""

    path: str
    description: str
    type: str
    mutable: bool = True
    constraints: list[str] = dataclass_field(default_factory=list)


GLOBAL_FIELD_SPECS: list[ConfigFieldSpec] = [
    ConfigFieldSpec(
        path="consensus.buy",
        description="Consensus threshold that must be reached for a BUY signal.",
        type="decimal", mutable=True, constraints=["value > 0", "value >= 0.05", "value <= 10.0"],
    ),
    ConfigFieldSpec(
        path="consensus.sell",
        description="Consensus threshold that must be reached for a SELL signal.",
        type="decimal", mutable=True, constraints=["value > 0", "value >= 0.05", "value <= 10.0"],
    ),
    ConfigFieldSpec(
        path="dynamic_quantity",
        description="Expression computing the quantity to buy. May reference indicators and the symbol `eq`.",
        type="string", mutable=True,
        constraints=["value is a non-empty string"],
    ),
    ConfigFieldSpec(
        path="llm.provider",
        description="Which LLM provider is used. Changing it requires a restart.",
        type="enum", mutable=False,
    ),
    ConfigFieldSpec(
        path="llm.model",
        description="Model identifier used with the configured provider. Changing it requires a restart.",
        type="string", mutable=False,
    ),
    ConfigFieldSpec(
        path="llm.temperature",
        description="Sampling temperature of the LLM.",
        type="decimal", mutable=True, constraints=["0.0 <= value <= 2.0"],
    ),
    ConfigFieldSpec(
        path="llm.timeout",
        description="Request timeout in seconds for LLM calls.",
        type="decimal", mutable=True, constraints=["value >= 1.0"],
    ),
    ConfigFieldSpec(
        path="llm.api_key",
        description="Secret API key for cloud providers. Never exposed or modified by the agent.",
        type="string", mutable=False,
    ),
    ConfigFieldSpec(
        path="llm.base_url",
        description="Provider endpoint override. Changing it requires a restart.",
        type="string", mutable=False,
    ),
    ConfigFieldSpec(
        path="llm.keep_alive",
        description="Keep-alive window for local Ollama models. Changing it requires a restart.",
        type="string", mutable=False,
    ),
    ConfigFieldSpec(
        path="llm.schedule",
        description="How often the LLM analysis scheduler runs.",
        type="enum", mutable=True,
        constraints=["value in {0,1,2,3,4,5}"],
    ),
]

ASSET_FIELD_SPECS: list[ConfigFieldSpec] = [
    ConfigFieldSpec(
        path="assets.{{symbol}}.name",
        description="Human-readable display name of the asset.",
        type="string", mutable=False,
    ),
    ConfigFieldSpec(
        path="assets.{{symbol}}.base_ticker_symbol",
        description="Base currency of the trading pair (e.g. BTC).",
        type="string", mutable=False,
    ),
    ConfigFieldSpec(
        path="assets.{{symbol}}.quote_ticker_symbol",
        description="Quote currency of the trading pair (e.g. USD).",
        type="string", mutable=False,
    ),
    ConfigFieldSpec(
        path="assets.{{symbol}}.exchange",
        description="Exchange the asset is traded on.",
        type="enum", mutable=False,
    ),
    ConfigFieldSpec(
        path="assets.{{symbol}}.min_quantity",
        description="Minimum tradeable quantity for this asset.",
        type="decimal", mutable=True, constraints=["value > 0"],
    ),
    ConfigFieldSpec(
        path="assets.{{symbol}}.quote_decimals",
        description="Number of decimals used for quote amounts.",
        type="int", mutable=False,
    ),
    ConfigFieldSpec(
        path="assets.{{symbol}}.quantity_decimals",
        description="Number of decimals used for quantities.",
        type="int", mutable=False,
    ),
    ConfigFieldSpec(
        path="assets.{{symbol}}.candles_timeframe",
        description="Candle timeframe used to feed the strategy (e.g. MIN1).",
        type="enum", mutable=False,
    ),
    ConfigFieldSpec(
        path="assets.{{symbol}}.schedule",
        description="Trading cadence for this asset: 0=second, 1=minute, 2=hour, 3=day, 4=week, 5=month.",
        type="int", mutable=True, constraints=["value in {0,1,2,3,4,5}"],
    ),
    ConfigFieldSpec(
        path="assets.{{symbol}}.guard_config.max_drawdown_period",
        description="Number of candles over which max drawdown is measured before trading halts.",
        type="int", mutable=True, constraints=["value >= 1", "value <= 10000"],
    ),
    ConfigFieldSpec(
        path="assets.{{symbol}}.guard_config.max_drawdown_percentage",
        description="Maximum tolerated drawdown fraction (0.60 means 60%) before trading halts.",
        type="decimal", mutable=True, constraints=["0 < value <= 1"],
    ),
    ConfigFieldSpec(
        path="assets.{{symbol}}.guard_config.cooldown_timeout",
        description="Seconds to wait after a drawdown halt before trading resumes.",
        type="int", mutable=True, constraints=["value >= 0"],
    ),
]


_RANGE_TEMPLATE = re.compile(
    r"^(?P<lo>[+-]?\d+(?:\.\d+)?)\s*<=\s*value\s*<=\s*(?P<hi>[+-]?\d+(?:\.\d+)?)$"
)
_COMPARISON_TEMPLATE = re.compile(
    r"^value\s*(?P<op><=|>=|<|>)\s*(?P<num>[+-]?\d+(?:\.\d+)?)$"
)
_SET_TEMPLATE = re.compile(r"^value\s+in\s+\{(.*)\}$")

_COMPARISONS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}


class ConfigurationSchema:
    @staticmethod
    def asset_symbol(asset_entry: dict) -> str:
        return f"{asset_entry.get('base_ticker_symbol', '?')}_{asset_entry.get('quote_ticker_symbol', '?')}"

    @staticmethod
    def find_asset_entry(raw_config: dict, symbol: str) -> Optional[dict]:
        for entry in raw_config.get("assets", []):
            if ConfigurationSchema.asset_symbol(entry) == symbol:
                return entry
        return None

    @staticmethod
    def _descend_path(current: dict, fragments: list[str]) -> Any:
        value: Any = current
        for fragment in fragments:
            if not isinstance(value, dict) or fragment not in value:
                return None
            value = value[fragment]
        return value

    @staticmethod
    def get_value(raw_config: dict, path: str) -> Any:
        fragments = path.split(".")
        if fragments[0] == "assets" and len(fragments) >= 3:
            entry = ConfigurationSchema.find_asset_entry(raw_config, fragments[1])
            if entry is None:
                return None
            return ConfigurationSchema._descend_path(entry, fragments[2:])
        return ConfigurationSchema._descend_path(raw_config, fragments)

    @staticmethod
    def set_value(raw_config: dict, path: str, value: Any) -> bool:
        fragments = path.split(".")
        if fragments[0] == "assets" and len(fragments) >= 3:
            entry = ConfigurationSchema.find_asset_entry(raw_config, fragments[1])
            if entry is None:
                return False
            return ConfigurationSchema._set_descend(entry, fragments[2:], value)
        return ConfigurationSchema._set_descend(raw_config, fragments, value)

    @staticmethod
    def _set_descend(current: dict, fragments: list[str], value: Any) -> bool:
        target = current
        for fragment in fragments[:-1]:
            if not isinstance(target, dict) or fragment not in target:
                return False
            target = target[fragment]
        if not isinstance(target, dict) or fragments[-1] not in target:
            return False
        target[fragments[-1]] = value
        return True

    def build_field_catalog(self, raw_config: dict) -> list[ConfigField]:
        fields: list[ConfigField] = []
        for spec in GLOBAL_FIELD_SPECS:
            fields.append(self._materialize(spec, raw_config, path=spec.path))

        for entry in raw_config.get("assets", []):
            symbol = self.asset_symbol(entry)
            for spec in ASSET_FIELD_SPECS:
                path = spec.path.replace("{{symbol}}", symbol)
                fields.append(self._materialize(spec, raw_config, path=path))
        return fields

    def _materialize(self, spec: ConfigFieldSpec, raw_config: dict, path: str) -> ConfigField:
        return ConfigField(
            path=path,
            value=self.get_value(raw_config, path),
            description=spec.description,
            type=spec.type,
            mutable=spec.mutable,
            constraints=spec.constraints,
        )

    def render_catalog(self, fields: list[ConfigField]) -> str:
        lines = ["Current configuration fields available to change:"]
        for field in sorted(fields, key=lambda f: f.path):
            mut = "editable" if field.mutable else "locked"
            lines.append(
                f"- {field.path} [{mut}, {field.type}] = {field.value!r} "
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
        stripped = constraint.strip()

        range_match = _RANGE_TEMPLATE.match(stripped)
        if range_match:
            number = ConfigurationSchema._as_number(value)
            if number is not None:
                return float(range_match.group("lo")) <= number <= float(range_match.group("hi"))

        comparison_match = _COMPARISON_TEMPLATE.match(stripped)
        if comparison_match:
            number = ConfigurationSchema._as_number(value)
            if number is not None:
                return _COMPARISONS[comparison_match.group("op")](number, float(comparison_match.group("num")))

        set_match = _SET_TEMPLATE.match(stripped)
        if set_match:
            allowed = {item.strip() for item in set_match.group(1).split(",")}
            return str(value) in allowed

        if stripped == "value is a non-empty string":
            return isinstance(value, str) and len(value.strip()) > 0

        return True
