from __future__ import annotations

from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.configuration.models import ValidationResult
from src.agent.configuration.state import ConfigurationAgentState


class ValidateProposalNode:
    def __init__(self, configuration_service: ConfigurationService):
        self._configuration_service = configuration_service

    def __call__(self, state: ConfigurationAgentState) -> dict:
        validation: ValidationResult = self._configuration_service.validate_proposal(state["proposal"])
        validation = self._apply_scoping_warnings(validation, state)
        return {"validation": validation}

    @staticmethod
    def _apply_scoping_warnings(validation: ValidationResult, state: ConfigurationAgentState) -> ValidationResult:
        request = state.get("request")
        if not request or not request.goal or not request.goal.target_asset:
            return validation
        proposal = state["proposal"]
        asset_prefix = f"assets.{request.goal.target_asset}."
        for change in proposal.changes:
            if not change.path.startswith(asset_prefix):
                validation.warnings.append(
                    f"Request was scoped to asset {request.goal.target_asset}, but '{change.path}' is a global "
                    "setting that applies to all assets."
                )
        return validation
