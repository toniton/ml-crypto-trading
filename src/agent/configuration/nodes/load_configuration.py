from __future__ import annotations

from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.configuration.state import ConfigurationAgentState


class LoadConfigurationNode:
    def __init__(self, configuration_service: ConfigurationService):
        self._configuration_service = configuration_service

    def __call__(self, state: ConfigurationAgentState) -> dict:
        return {"catalog_context": self._configuration_service.render_catalog()}
