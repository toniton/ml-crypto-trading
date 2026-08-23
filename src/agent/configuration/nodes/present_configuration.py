from __future__ import annotations

from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.configuration.models import ConfigurationPresentation, MarkdownBlock
from src.agent.configuration.state import ConfigurationAgentState


class PresentConfigurationNode:
    def __init__(self, configuration_service: ConfigurationService):
        self._configuration_service = configuration_service

    def __call__(self, state: ConfigurationAgentState) -> dict:
        request = state.get("request")
        target_asset = request.goal.target_asset if request and request.goal else None
        if target_asset:
            view = self._configuration_service.build_configuration_view(target_asset)
            presentation = ConfigurationPresentation(blocks=[view])
        else:
            content = self._configuration_service.render_configuration_view()
            presentation = ConfigurationPresentation(blocks=[MarkdownBlock.from_text(content)])
        return {"presentation": presentation}
