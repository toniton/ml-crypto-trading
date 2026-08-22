from __future__ import annotations

from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.configuration.state import ConfigurationAgentState


class PresentProposalNode:
    def __init__(self, configuration_service: ConfigurationService):
        self._configuration_service = configuration_service

    def __call__(self, state: ConfigurationAgentState) -> dict:
        validation = state.get("validation")
        warnings = validation.warnings if validation else []
        errors = validation.errors if validation and not validation.valid else []
        presentation = self._configuration_service.build_presentation(
            state["proposal"], warnings=warnings, errors=errors
        )
        return {"presentation": presentation}
