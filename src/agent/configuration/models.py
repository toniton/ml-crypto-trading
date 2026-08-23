from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field

from src.agent.router.models import AgentGoal, AgentIntent

# Backwards-compatible alias: goal extraction now lives in the router.
ConfigurationGoal = AgentGoal


class ProposalDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"

    @property
    def label(self) -> str:
        return "Approved" if self is ProposalDecision.APPROVE else "Rejected"


class ConfigChange(BaseModel):
    path: str = Field(description="Dot-separated config path, e.g. 'assets.BTC_USD.schedule'.")
    old_value: Any = Field(description="The current value of the field.")
    new_value: Any = Field(description="The proposed replacement value.")
    reason: str = Field(description="Why this change is required to reach the user's goal.")


class ConfigurationProposal(BaseModel):
    summary: str = Field(description="Short human-readable summary of the proposal.")
    changes: list[ConfigChange] = Field(description="The patch entries to apply.")
    risks: list[str] = Field(default_factory=list, description="Potential downsides of the changes.")
    expected_effect: str = Field(
        default="",
        description="What behaviour change the user can expect once the proposal is applied.",
    )


class ValidationResult(BaseModel):
    valid: bool = Field(description="Whether the proposal can be applied as-is.")
    errors: list[str] = Field(default_factory=list, description="Human-readable validation failures.")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking observations.")

    @classmethod
    def ok(cls) -> ValidationResult:
        return cls(valid=True)

    @classmethod
    def failed(cls, errors: list[str]) -> ValidationResult:
        return cls(valid=False, errors=errors)


class MarkdownBlock(BaseModel):
    type: Literal["markdown"] = "markdown"
    content: str = Field(default="", description="Markdown content.")

    @classmethod
    def from_text(cls, content: str) -> MarkdownBlock:
        return cls(content=content)


class ConfigurationDiffBlock(BaseModel):
    type: Literal["configuration_diff"] = "configuration_diff"
    changes: list[ConfigChange] = Field(default_factory=list, description="The changes to render.")
    prefix: str = Field("", description="Optional heading rendered above the diff.")


class StatCard(BaseModel):
    label: str = Field(description="Caption above the value, e.g. 'Exchange'.")
    value: str = Field(description="Display value, e.g. 'CRYPTO.COM'.")
    tint: Literal["default", "buy", "sell"] = Field(
        default="default",
        description="Colour hint: 'buy'/'sell' for consensus thresholds, else 'default'.",
    )


class FieldRow(BaseModel):
    name: str = Field(description="Short field name, e.g. 'buy'.")
    path: str = Field(description="Full dot-separated path, e.g. 'assets.BTC_USD.consensus.buy'.")
    value: Any = Field(description="Current value of the field.")
    type: str = Field(description="Semantic type: decimal, int, bool, enum, or string.")
    mutable: bool = Field(description="Whether the field may be changed without a restart.")
    description: str = Field(default="", description="Plain-language explanation of the field's purpose.")
    constraints: list[str] = Field(default_factory=list, description="Machine-checkable constraints.")
    enum_values: list[str] = Field(
        default_factory=list,
        description="Allowed values for enum fields, rendered as chips.",
    )


class SectionCard(BaseModel):
    title: str = Field(description="Heading shown on the collapsible card, e.g. 'Consensus thresholds'.")
    path: str = Field(description="Config path that groups these fields.")
    description: str = Field(default="", description="One-line context shown under the heading.")
    fields: list[FieldRow] = Field(default_factory=list, description="The rows under this section.")


class StrategyCard(BaseModel):
    name: str = Field(description="Strategy identifier, e.g. 'RsiOversoldBuy'.")
    path: str = Field(description="Config path for the strategy, e.g. 'assets.BTC_USD.strategies.RsiOversoldBuy'.")
    action: str = Field(description="Vote direction: BUY or SELL.")
    kind: str = Field(description="Implementation type: STATIC or DYNAMIC.")
    enabled: Optional[bool] = Field(default=None, description="Active flag, or None when unset.")
    expression: Optional[str] = Field(default=None, description="DYNAMIC strategy expression.")
    class_name: Optional[str] = Field(default=None, description="STATIC strategy class name.")


class SignalWindow(BaseModel):
    min: float = Field(description="Left edge of the consensus scale.")
    sell: float = Field(description="Sell threshold position on the scale.")
    buy: float = Field(description="Buy threshold position on the scale.")
    max: float = Field(description="Right edge of the consensus scale.")


class ConfigurationViewBlock(BaseModel):
    type: Literal["configuration_view"] = "configuration_view"
    asset: str = Field(description="Market symbol shown in the header, e.g. 'BTC_USD'.")
    name: str = Field(description="Human-readable asset name.")
    base: str = Field(description="Base ticker symbol.")
    quote: str = Field(description="Quote ticker symbol.")
    stats: list[StatCard] = Field(default_factory=list, description="Top summary cards.")
    sections: list[SectionCard] = Field(default_factory=list, description="Grouped field cards.")
    strategies: list[StrategyCard] = Field(default_factory=list, description="Strategy stack cards.")
    signal_window: Optional[SignalWindow] = Field(default=None, description="Consensus gauge if thresholds exist.")
    editable_count: int = Field(default=0, description="Number of editable fields.")
    field_count: int = Field(default=0, description="Total number of fields.")


class ApprovalAction(BaseModel):
    id: str = Field(description="Stable identifier for the action, e.g. 'approve'.")
    label: str = Field(description="Human-readable label shown in the UI, e.g. 'Approve'.")


class ApprovalBlock(BaseModel):
    type: Literal["approval"] = "approval"
    actions: list[ApprovalAction] = Field(
        default_factory=lambda: [
            ApprovalAction(id="approve", label="Approve"),
            ApprovalAction(id="reject", label="Reject"),
        ],
        description="The choices offered, as id/label pairs.",
    )

    @classmethod
    def build(cls) -> ApprovalBlock:
        return cls()


UIBlock = Union[MarkdownBlock, ConfigurationDiffBlock, ApprovalBlock, ConfigurationViewBlock]


class ConfigurationPresentation(BaseModel):
    blocks: list[UIBlock] = Field(default_factory=list, description="Ordered UI blocks to render.")

    @classmethod
    def empty(cls) -> ConfigurationPresentation:
        return cls(blocks=[])

    def markdown(self) -> str:
        """Renders the blocks back to a plain markdown string."""
        lines: list[str] = []
        for block in self.blocks:
            if isinstance(block, MarkdownBlock):
                lines.append(block.content)
            elif isinstance(block, ConfigurationDiffBlock):
                for change in block.changes:
                    lines.append(f"- {change.path}: {change.old_value!r} -> {change.new_value!r}")
                    lines.append(f"    reason: {change.reason}")
            elif isinstance(block, ApprovalBlock):
                lines.append(f"Actions: {', '.join(action.label for action in block.actions)}")
            elif isinstance(block, ConfigurationViewBlock):
                lines.append(f"# {block.base} / {block.quote} — {block.name}")
                lines.append(f"`{block.asset}` · {block.field_count} fields · {block.editable_count} editable")
                for section in block.sections:
                    lines.append(f"\n## {section.title}")
                    for field in section.fields:
                        lines.append(f"- `{field.path}` [{field.type}] = {field.value!r}")
                        if field.description:
                            lines.append(f"    {field.description}")
        return "\n".join(line for line in lines if line)


class ConfigurationResult(BaseModel):
    kind: Literal["configuration"] = "configuration"
    goal: AgentGoal
    proposal: Optional[ConfigurationProposal] = None
    validation: Optional[ValidationResult] = None
    presentation: ConfigurationPresentation


class ClarificationResult(BaseModel):
    kind: Literal["clarification"] = "clarification"
    question: str = Field(description="The question to ask the user.")
    intent: AgentIntent = Field(
        default=AgentIntent.GENERAL,
        description="The agent the request was being routed toward.",
    )
    goal: Optional[AgentGoal] = Field(
        default=None,
        description="The partial goal, if any, extracted before clarification.",
    )


class GeneralResult(BaseModel):
    kind: Literal["general"] = "general"
