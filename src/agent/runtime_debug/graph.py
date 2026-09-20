from __future__ import annotations

from typing import Optional

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agent.runtime_debug.nodes.diagnose_node import DiagnoseNode
from src.agent.runtime_debug.nodes.generate_suggestion_node import GenerateSuggestionNode
from src.agent.runtime_debug.nodes.investigate_node import InvestigateNode
from src.agent.runtime_debug.nodes.load_context_node import LoadContextNode
from src.agent.runtime_debug.nodes.present_suggestion_node import PresentSuggestionNode
from src.agent.runtime_debug.nodes.validate_diagnosis_node import ValidateDiagnosisNode
from src.agent.runtime_debug.playbooks.playbook_resolver import PlaybookResolver
from src.agent.runtime_debug.state import RuntimeDebugState
from src.agent.runtime_debug.tools import RuntimeDebugToolbox
from src.core.interfaces.llm_adapter import LlmAdapter


class RuntimeDebugGraph:
    def __init__(
            self,
            toolbox: RuntimeDebugToolbox,
            llm: Optional[LlmAdapter] = None,
            playbook_resolver: Optional[PlaybookResolver] = None,
    ):
        self._toolbox = toolbox
        self._llm = llm
        self._playbook_resolver = playbook_resolver or PlaybookResolver()

    def build(self) -> CompiledStateGraph:
        builder = StateGraph(RuntimeDebugState)

        builder.add_node("load_context", LoadContextNode(self._toolbox))
        builder.add_node("investigate", InvestigateNode(self._toolbox, self._playbook_resolver))
        builder.add_node("diagnose", DiagnoseNode(self._llm))
        builder.add_node("validate_diagnosis", ValidateDiagnosisNode())
        builder.add_node("generate_suggestion", GenerateSuggestionNode(self._llm))
        builder.add_node("present_suggestion", PresentSuggestionNode())

        builder.add_edge(START, "load_context")
        builder.add_edge("load_context", "investigate")
        builder.add_edge("investigate", "diagnose")
        builder.add_edge("diagnose", "validate_diagnosis")
        builder.add_edge("validate_diagnosis", "generate_suggestion")
        builder.add_edge("generate_suggestion", "present_suggestion")
        builder.add_edge("present_suggestion", END)

        return builder.compile()
