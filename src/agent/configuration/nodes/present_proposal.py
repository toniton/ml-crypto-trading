from __future__ import annotations

from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.configuration.state import ConfigurationAgentState


class PresentProposalNode:
    def __init__(self, configuration_service: ConfigurationService):
        self._configuration_service = configuration_service

    def __call__(self, state: ConfigurationAgentState) -> dict:
        warnings = []
        validation = state.get("validation")
        if validation and validation.warnings:
            warnings = validation.warnings
        presentation = self._configuration_service.build_presentation(state["proposal"], warnings=warnings)
        return {"presentation": presentation}
