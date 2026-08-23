from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.core.interfaces.llm_adapter import LlmAdapter
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.configuration.nodes.generate_proposal import GenerateProposalNode
from src.agent.configuration.nodes.load_configuration import LoadConfigurationNode
from src.agent.configuration.nodes.present_configuration import PresentConfigurationNode
from src.agent.configuration.nodes.present_proposal import PresentProposalNode
from src.agent.configuration.nodes.validate_proposal import ValidateProposalNode
from src.agent.configuration.state import ConfigurationAgentState
from src.agent.router.models import ConfigurationAction

MAX_GENERATION_ATTEMPTS = 2


class ConfigurationGraph:
    def __init__(
            self,
            llm: LlmAdapter,
            configuration_service: ConfigurationService,
    ):
        self._llm = llm
        self._configuration_service = configuration_service

    @staticmethod
    def route_after_validation(state: ConfigurationAgentState) -> str:
        validation = state.get("validation")
        if validation and not validation.valid and state.get("proposal_attempts", 0) < MAX_GENERATION_ATTEMPTS:
            return "regenerate"
        return "present"

    @staticmethod
    def route_by_action(state: ConfigurationAgentState) -> str:
        request = state.get("request")
        if request and request.action == ConfigurationAction.VIEW:
            return "view"
        return "modify"

    def build(self) -> CompiledStateGraph:
        builder = StateGraph(ConfigurationAgentState)

        builder.add_node("load_configuration", LoadConfigurationNode(self._configuration_service))
        builder.add_node("generate_proposal", GenerateProposalNode(self._llm, self._configuration_service))
        builder.add_node("validate_proposal", ValidateProposalNode(self._configuration_service))
        builder.add_node("present_proposal", PresentProposalNode(self._configuration_service))
        builder.add_node("present_configuration", PresentConfigurationNode(self._configuration_service))

        builder.add_edge(START, "load_configuration")
        builder.add_conditional_edges(
            "load_configuration",
            self.route_by_action,
            {
                "view": "present_configuration",
                "modify": "generate_proposal",
            },
        )
        builder.add_edge("present_configuration", END)
        builder.add_edge("generate_proposal", "validate_proposal")
        builder.add_conditional_edges(
            "validate_proposal",
            self.route_after_validation,
            {
                "regenerate": "generate_proposal",
                "present": "present_proposal",
            },
        )
        builder.add_edge("present_proposal", END)

        return builder.compile()
