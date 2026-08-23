from __future__ import annotations

import uuid
from typing import Any, AsyncIterator, List, Optional, Union

from src.core.interfaces.llm_adapter import ChatTurn, LlmAdapter
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.configuration.graph import ConfigurationGraph
from src.agent.configuration.models import ClarificationResult, ConfigurationResult, GeneralResult
from src.agent.router.graph import RouterGraph
from src.agent.router.models import AgentIntent, AgentRoute
from src.agent.runtime.agent import AgentDefinition
from src.agent.runtime.registry import AgentRegistry
from src.agent.events import AIEvent
from src.llm.math_normalizer import DelimiterStream

AgentResult = Union[ConfigurationResult, ClarificationResult, GeneralResult]


class AgentGateway:
    def __init__(
            self,
            llm: LlmAdapter,
            config_filepath: str,
            registry: Optional[AgentRegistry] = None,
    ):
        self._llm = llm
        self._registry = registry or self.build_default_registry(llm, config_filepath)
        self._router = RouterGraph(llm, self._registry.agent_name_for).build()

    def handle(self, prompt: str, history: Optional[List[ChatTurn]] = None) -> AgentResult:
        route = self._route(prompt)
        if route.requires_clarification:
            return ClarificationResult(
                question=route.clarification_question or "",
                intent=route.intent,
                goal=route.goal,
            )
        definition = self._registry.get(route.intent)
        if definition.graph is None:
            return GeneralResult()

        state = definition.graph.invoke({"user_prompt": prompt, "request": route, "history": history or []})
        return ConfigurationResult(
            goal=route.goal,
            proposal=state["proposal"],
            validation=state["validation"],
            presentation=state["presentation"],
        )

    def _route(self, prompt: str) -> AgentRoute:
        state = self._router.invoke({"user_prompt": prompt})
        return state.get("route") or AgentRoute(intent=AgentIntent.GENERAL)

    async def stream(  # pylint: disable=too-many-locals
            self,
            prompt: str,
            history: Optional[List[ChatTurn]] = None,
            message_id: Optional[str] = None,
    ) -> AsyncIterator[AIEvent]:
        message_id = message_id or uuid.uuid4().hex
        captures: dict[str, Any] = {}

        async for event in self._router.astream_events(
            {"user_prompt": prompt},
            version="v2",
        ):
            mapped = self._map_stream_event(event, message_id, agent="router", captures=captures)
            if mapped is not None:
                yield mapped

        route: Optional[AgentRoute] = captures.get("route") or AgentRoute(intent=AgentIntent.GENERAL)
        if route.requires_clarification:
            yield AIEvent(
                type="clarification",
                message_id=message_id,
                payload={
                    "question": route.clarification_question or "",
                    "intent": route.intent.value,
                    "goal": route.goal,
                },
            )
            yield AIEvent(type="done", message_id=message_id, payload={"kind": "clarification"})
            return

        agent_name: str = captures.get("agent") or self._registry.agent_name_for(route.intent)
        definition = self._registry.get_by_name(agent_name) or self._registry.get(route.intent)

        if definition.graph is None:
            sanitizer = DelimiterStream()
            async for chunk in self._llm.stream(prompt, history=history):
                if chunk:
                    text = sanitizer.push(str(chunk))
                    if text:
                        yield AIEvent(
                            type="token",
                            message_id=message_id,
                            agent=definition.name,
                            payload=text,
                        )
            tail = sanitizer.flush()
            if tail:
                yield AIEvent(
                    type="token",
                    message_id=message_id,
                    agent=definition.name,
                    payload=tail,
                )
            yield AIEvent(type="done", message_id=message_id, agent=definition.name,
                          payload={"kind": definition.name})
            return

        block_index = 0
        async for event in definition.graph.astream_events(
            {"user_prompt": prompt, "request": route, "history": history or []},
            version="v2",
        ):
            mapped = self._map_stream_event(
                event,
                message_id,
                agent=definition.name,
                captures=captures,
                presentation_node=definition.presentation_node,
            )
            if mapped is not None:
                yield mapped
            presentation = captures.pop("presentation", None)
            if presentation is None:
                continue
            for block in presentation.blocks:
                block_index += 1
                yield AIEvent(
                    type="block",
                    message_id=message_id,
                    id=f"b{block_index}",
                    agent=definition.name,
                    payload=block,
                )

        done_payload: dict[str, Any] = {"kind": definition.name}
        proposal = captures.get("proposal")
        if proposal is not None:
            done_payload["proposal"] = proposal
        yield AIEvent(type="done", message_id=message_id, agent=definition.name, payload=done_payload)

    @staticmethod
    def build_default_registry(
        llm: LlmAdapter,
        config_filepath: str,
    ) -> AgentRegistry:
        configuration_service = ConfigurationService(config_filepath)
        definitions = [
            AgentDefinition(
                name="configuration",
                description="Creates and validates trading configuration changes",
                graph=ConfigurationGraph(llm, configuration_service).build(),
                presentation_node="present_proposal",
                capabilities=frozenset({"trading_config.read", "asset_config.read", "config.propose"}),
            ),
            AgentDefinition(
                name="general",
                description="Answers general questions and any request without a specialized agent",
                capabilities=frozenset(),
            ),
            AgentDefinition(
                name="performance_analysis",
                description="Analyzes trading performance and why strategies behaved a certain way",
                capabilities=frozenset({"reports.read", "logs.read", "trading_config.read"}),
            ),
            AgentDefinition(
                name="risk_analysis",
                description="Analyzes exposure, drawdown, position sizing, and risk-adjusted returns",
                capabilities=frozenset({"trading_config.read", "asset_balance.read", "reports.read"}),
            ),
            AgentDefinition(
                name="market_analysis",
                description="Analyzes markets, news, and sentiment",
                capabilities=frozenset({"news.read", "sentiment.read"}),
            ),
            AgentDefinition(
                name="reporting",
                description="Produces reports and activity summaries",
                capabilities=frozenset({"reports.read", "trade_logs.read"}),
            ),
            AgentDefinition(
                name="system_help",
                description="Explains what the bot can do and how to use it",
                capabilities=frozenset(),
            ),
        ]
        registry = AgentRegistry(definitions)
        for intent, name in (
            (AgentIntent.CONFIGURATION, "configuration"),
            (AgentIntent.PERFORMANCE_ANALYSIS, "performance_analysis"),
            (AgentIntent.RISK_ANALYSIS, "risk_analysis"),
            (AgentIntent.MARKET_ANALYSIS, "market_analysis"),
            (AgentIntent.REPORTING, "reporting"),
            (AgentIntent.SYSTEM_HELP, "system_help"),
            (AgentIntent.GENERAL, "general"),
        ):
            registry.register(intent, name)
        return registry

    @staticmethod
    def _map_stream_event(
            event: dict,
            message_id: str,
            agent: str,
            captures: dict[str, Any],
            presentation_node: Optional[str] = None,
    ) -> Optional[AIEvent]:
        node = event.get("metadata", {}).get("langgraph_node")
        if not node or node.startswith("__") or event.get("name") != node:
            return None

        if event["event"] == "on_chain_start":
            return AIEvent(type="node_started", message_id=message_id, agent=agent, payload={"node": node})

        if event["event"] == "on_chain_end":
            output = event["data"].get("output") or {}
            if node == "understand_goal":
                captures["route"] = output.get("route")
            elif node == "route":
                captures["agent"] = output.get("agent")
            elif node == presentation_node:
                captures["presentation"] = output.get("presentation")
            if isinstance(output, dict) and "proposal" in output:
                captures["proposal"] = output["proposal"]
            return AIEvent(type="node_completed", message_id=message_id, agent=agent, payload={"node": node})

        return None
