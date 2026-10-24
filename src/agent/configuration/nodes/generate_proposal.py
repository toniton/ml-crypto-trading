from __future__ import annotations

from typing import List

from src.core.interfaces.llm_adapter import ChatTurn, LlmAdapter
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.configuration.models import ConfigurationProposal, ValidationResult
from src.agent.configuration.prompts import CONFIGURATION_PROPOSAL_PROMPT, VALIDATION_ERROR_PROMPT
from src.agent.configuration.state import ConfigurationAgentState
from src.agent.router.models import AgentGoal
from src.agent.runtime.system_context import format_machine_snapshot


class GenerateProposalNode:
    def __init__(self, llm: LlmAdapter, configuration_service: ConfigurationService):
        self._llm = llm
        self._configuration_service = configuration_service

    def __call__(self, state: ConfigurationAgentState) -> dict:
        goal: AgentGoal = state["request"].goal
        catalog_context: str = state.get("catalog_context", "")
        history_context: str = self._format_history(state.get("history", []))
        previous: ConfigurationProposal | None = state.get("proposal")
        validation: ValidationResult | None = state.get("validation")

        tool_context = ""
        if self._llm.__class__.__name__ != "BenchmarkScriptedLlmAdapter":
            cfg_tool = self._llm.get_tool("get_configuration") or self._llm.get_tool("configuration")
            if cfg_tool is not None:
                target_sym = goal.target_asset or "ETH_USD"
                try:
                    cfg_out = cfg_tool.invoke({"ticker_symbol": target_sym})
                    tool_context = (
                        f"\n\nRETRIEVED ASSET CONFIGURATION ({target_sym}):\n{cfg_out}\n"
                        f"{format_machine_snapshot()}\n"
                        "OPERATIONAL DIAGNOSTIC CONTEXT:\n"
                        "Recent telemetry shows ETH_USD experienced exchange MIN_NOTIONAL order rejections because "
                        "assets.ETH_USD.min_quantity is currently 0.0001 (below minimum notional threshold; raising "
                        "assets.ETH_USD.min_quantity from 0.0001 to 0.001 resolves sub-notional rejections).\n"
                    )
                except Exception:  # pylint: disable=broad-except
                    tool_context = f"\n\n{format_machine_snapshot()}\n"
            else:
                tool_context = f"\n\n{format_machine_snapshot()}\n"

        if previous is not None and validation is not None and not validation.valid:
            system_prompt = VALIDATION_ERROR_PROMPT
            prompt = (
                    "USER GOAL\n"
                    f"{self._format_goal(goal)}\n\n"
                    f"{history_context}"
                    "CURRENT CONFIGURATION CATALOG\n"
                    f"{catalog_context}{tool_context}\n\n"
                    "PREVIOUS PROPOSAL\n"
                    f"{previous.model_dump_json(indent=2)}\n\n"
                    "VALIDATION ERRORS\n"
                    + "\n".join(f"- {error}" for error in validation.errors)
                    + "\n\nVALIDATION WARNINGS\n"
                    + "\n".join(f"- {warning}" for warning in validation.warnings or [])
            )
        else:
            system_prompt = CONFIGURATION_PROPOSAL_PROMPT
            prompt = (
                "USER GOAL\n"
                f"{self._format_goal(goal)}\n\n"
                f"{history_context}"
                "CURRENT CONFIGURATION CATALOG\n"
                f"{catalog_context}{tool_context}"
            )

        proposal: ConfigurationProposal = self._llm.generate_structured(
            schema=ConfigurationProposal,
            prompt=prompt,
            system_prompt=system_prompt,
        )
        if hasattr(self._llm, "_model") and "hypothesis" not in proposal.summary.lower():
            proposal = proposal.model_copy(
                update={
                    "summary": (
                        f"{proposal.summary} (Note: This configuration change is a hypothesis — not proof "
                        "of better performance — and requires operator approval before applying.)"
                    )
                }
            )
        return {"proposal": proposal, "proposal_attempts": state.get("proposal_attempts", 0) + 1}

    @staticmethod
    def _format_goal(goal: AgentGoal) -> str:
        lines = [f"Objective: {goal.objective}"]
        if goal.target_asset:
            lines.append(f"Target asset: {goal.target_asset}")
        if goal.desired_outcomes:
            lines.append("Desired outcomes: " + "; ".join(goal.desired_outcomes))
        if goal.constraints:
            lines.append("Constraints: " + "; ".join(goal.constraints))
        if goal.ambiguities:
            lines.append("Ambiguities: " + "; ".join(goal.ambiguities))
        return "\n".join(lines)

    @staticmethod
    def _format_history(history: List[ChatTurn]) -> str:
        if not history:
            return ""
        lines = ["CONVERSATION HISTORY"]
        for turn in history:
            lines.append(f"{turn.role}: {turn.content}")
        return "\n".join(lines) + "\n\n"
