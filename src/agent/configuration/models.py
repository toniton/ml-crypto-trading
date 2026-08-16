from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field

from src.agent.router.models import AgentGoal

# Backwards-compatible alias: goal extraction now lives in the router.
ConfigurationGoal = AgentGoal


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


UIBlock = Union[MarkdownBlock, ConfigurationDiffBlock, ApprovalBlock]


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
        return "\n".join(line for line in lines if line)


class ConfigurationResult(BaseModel):
    kind: Literal["configuration"] = "configuration"
    goal: AgentGoal
    proposal: ConfigurationProposal
    validation: ValidationResult
    presentation: ConfigurationPresentation


class GeneralResult(BaseModel):
    kind: Literal["general"] = "general"
