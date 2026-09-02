import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.agent import AgentGateway
from src.agent import (
    ConfigChange,
    ConfigurationProposal,
)
from src.agent.router.models import AgentGoal, AgentIntent, AgentRoute, ConfigurationAction
from src.server.app import ChatApp
from src.server.server import ApiServer
from src.events.message_event_bus import MessageEventBus
from src.llm.tools.metrics_tool import MetricsTool
from src.metrics.services.metric_service import MetricService
from tests.unit.agent.fakes import FakeLlmAdapter
from tests.unit.api_server.helpers import make_temp_db_manager


SAMPLE_CONFIG = """
assets:
  - name: "Bitcoin"
    base_ticker_symbol: "BTC"
    quote_ticker_symbol: "USD"
    exchange: "CRYPTO_DOT_COM"
    min_quantity: 0.00005
    quote_decimals: 2
    quantity_decimals: 5
    candles_timeframe: "MIN1"
    schedule: 1
    consensus:
      buy: 1.3
      sell: 0.5
"""


_TEST_CONFIG_DIR = tempfile.mkdtemp(prefix="agent-api-tests-")
_TEST_CONFIG_PATH = os.path.join(_TEST_CONFIG_DIR, "trading-config.yaml")
with open(_TEST_CONFIG_PATH, "w", encoding="utf-8") as handle:
    handle.write(SAMPLE_CONFIG)


def build_gateway(llm):
    return AgentGateway(llm, _TEST_CONFIG_PATH)


def build_app(llm):
    return ChatApp.create(
        agent=build_gateway(llm),
        event_bus=MessageEventBus(),
        db_manager=make_temp_db_manager(),
    )


class TestApiServerApp(unittest.TestCase):
    def setUp(self):
        self.llm = FakeLlmAdapter(chunks=["Token1 ", "Token2 ", "Token3"])
        self.app = build_app(self.llm)
        self.client = TestClient(self.app)

    def test_chat_endpoint_streaming_success(self):
        response = self.client.post("/api/v1/chat", json={"prompt": "Analyze BTC"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue("text/event-stream" in response.headers["content-type"])
        content = response.text
        self.assertIn("event: token", content)
        self.assertIn("data: ", content)
        self.assertIn("Token1", content)
        self.assertIn("Token3", content)
        self.assertIn("event: done", content)

    def test_chat_endpoint_query_field_alias(self):
        response = self.client.post("/api/v1/chat", json={"query": "What is ETH price?"})
        self.assertEqual(response.status_code, 200)
        content = response.text
        self.assertIn("event: token", content)
        self.assertIn("Token1", content)

    def test_chat_endpoint_missing_prompt_and_query(self):
        response = self.client.post("/api/v1/chat", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Either 'prompt' or 'query' must be provided.", response.json()["detail"])

    def test_chat_endpoint_empty_prompt(self):
        response = self.client.post("/api/v1/chat", json={"prompt": "   "})
        self.assertEqual(response.status_code, 400)

    def test_chat_endpoint_no_agent(self):
        app_no_agent = build_app(self.llm)
        app_no_agent.state.agent = None
        client = TestClient(app_no_agent)
        response = client.post("/api/v1/chat", json={"prompt": "Hello"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("Agent is not configured.", response.json()["detail"])

    @patch("uvicorn.Server.run")
    def test_api_server_lifecycle(self, mock_uvicorn_run):
        server = ApiServer(
            agent=build_gateway(self.llm),
            event_bus=MessageEventBus(),
            db_manager=make_temp_db_manager(),
            host="127.0.0.1",
            port=9999,
        )
        server.start()
        self.assertIsNotNone(server._thread)
        server.stop()
        self.assertIsNotNone(server._server)
        self.assertTrue(server._server.should_exit)

    def test_configuration_prompt_streams_proposal_through_gateway(self):
        import json

        llm = FakeLlmAdapter([
            AgentRoute(
                intent=AgentIntent.CONFIGURATION,
                goal=AgentGoal(objective="take more trades"),
            ),
            ConfigurationProposal(
                summary="less conservative",
                changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.1, reason="more trades")],
            ),
        ])
        app = build_app(llm)
        client = TestClient(app)
        response = client.post("/api/v1/chat", json={"prompt": "make the strategy less conservative"})
        self.assertEqual(response.status_code, 200)

        events = []
        for raw in response.text.split("\n\n"):
            if not raw.strip():
                continue
            name, _, data = raw.partition("\n")
            events.append((name.split("event: ")[1], json.loads(data.split("data: ", 1)[1])))
        names = [name for name, _ in events]
        self.assertIn("node_started", names)
        self.assertIn("block", names)
        self.assertEqual(names[-1], "done")
        # exactly one node_started/node_completed per executed node (no duplicates)
        started = [data["payload"]["node"] for name, data in events if name == "node_started"]
        completed = [data["payload"]["node"] for name, data in events if name == "node_completed"]
        self.assertEqual(started, completed)
        # router (understand_goal, route) + configuration graph (4 nodes)
        self.assertEqual(len(started), 6)
        self.assertEqual(len(set(started)), len(started))
        # message_id correlated on every event
        message_ids = {data["message_id"] for _, data in events}
        self.assertEqual(len(message_ids), 1)
        self.assertTrue(len(message_ids.pop()) == 32)
        # block events carry ids and structured approval actions
        blocks = [data["payload"] for name, data in events if name == "block"]
        self.assertTrue(any(block["type"] == "configuration_diff" for block in blocks))
        self.assertTrue(any(block["type"] == "approval" for block in blocks))


class TestGatewayStreaming(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.addCleanup(self.loop.close)

    def collect(self, async_iter):
        return self.loop.run_until_complete(_collect(async_iter))

    def test_general_prompt_streams_llm_chunks(self):
        llm = FakeLlmAdapter(chunks=["a", "b", "c"])
        gateway = build_gateway(llm)
        events = self.collect(gateway.stream("Analyze BTC"))
        tokens = [event.payload for event in events if event.type == "token"]
        self.assertEqual(tokens, ["a", "b", "c"])
        self.assertEqual(events[-1].type, "done")

    def test_general_prompt_streams_normalized_math(self):
        llm = FakeLlmAdapter(
            chunks=[r"\[ 0.02282867 \tex", r"t{ BTC} \times $64,249.78/BTC", r" \approx $1,466.70 \]"],
        )
        gateway = build_gateway(llm)
        events = self.collect(gateway.stream("How rich am I?"))
        text = "".join(event.payload for event in events if event.type == "token")
        self.assertEqual(events[-1].type, "done")
        self.assertEqual(text.count("$$"), 2)
        self.assertIn(r"\text{ BTC}", text)
        self.assertIn(r"\times", text)
        self.assertIn(r"\approx", text)
        self.assertIn("$1,466.70", text)

    def test_configuration_prompt_streams_node_and_block_events(self):
        llm = FakeLlmAdapter([
            AgentRoute(
                intent=AgentIntent.CONFIGURATION,
                goal=AgentGoal(objective="take more trades"),
            ),
            ConfigurationProposal(
                summary="less conservative",
                changes=[ConfigChange(path="assets.BTC_USD.consensus.buy", old_value=1.3, new_value=1.1, reason="more trades")],
            ),
        ])
        gateway = build_gateway(llm)
        events = self.collect(gateway.stream("make the strategy less conservative"))
        node_events = [event.type for event in events]
        self.assertIn("node_started", node_events)
        self.assertIn("node_completed", node_events)
        blocks = [event.payload for event in events if event.type == "block"]
        self.assertTrue(any(block.type == "configuration_diff" for block in blocks))
        diff_block = next(b for b in blocks if b.type == "configuration_diff")
        self.assertEqual(diff_block.prefix, "Proposed changes")
        self.assertEqual(diff_block.changes[0].path, "assets.BTC_USD.consensus.buy")

    def test_view_configuration_prompt_streams_view_block_without_approval(self):
        llm = FakeLlmAdapter([
            AgentRoute(
                intent=AgentIntent.CONFIGURATION,
                action=ConfigurationAction.VIEW,
                goal=AgentGoal(objective="show BTC_USD config", target_asset="BTC_USD"),
            ),
        ])
        gateway = build_gateway(llm)
        events = self.collect(gateway.stream("show me configuration for BTC_USD"))
        blocks = [event.payload for event in events if event.type == "block"]
        self.assertTrue(any(block.type == "configuration_view" for block in blocks))
        self.assertFalse(any(block.type == "approval" for block in blocks))
        self.assertFalse(any(block.type == "markdown" for block in blocks))
        view = next(b for b in blocks if b.type == "configuration_view")
        self.assertEqual(view.asset, "BTC_USD")
        self.assertTrue(any(section.title == "Consensus thresholds" for section in view.sections))
        self.assertIsNotNone(view.signal_window)
        done = events[-1]
        self.assertEqual(done.type, "done")
        self.assertNotIn("proposal", done.payload)


class TestConversationSessions(unittest.TestCase):
    def test_session_event_emitted_with_id(self):
        llm = FakeLlmAdapter(chunks=["Token1 "])
        app = build_app(llm)
        client = TestClient(app)
        response = client.post("/api/v1/chat", json={"prompt": "Analyze BTC"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("event: session", response.text)
        self.assertTrue(_extract_session_id(response.text))

    def test_history_reused_across_requests(self):
        llm = FakeLlmAdapter(chunks=["ok"])
        app = build_app(llm)
        client = TestClient(app)

        first = client.post("/api/v1/chat", json={"prompt": "hello"})
        session_id = _extract_session_id(first.text)
        self.assertTrue(session_id)

        second = client.post("/api/v1/chat", json={"prompt": "follow up", "session_id": session_id})
        self.assertEqual(second.status_code, 200)
        history = llm.last_history
        self.assertIsNotNone(history)
        self.assertIn("hello", [turn.content for turn in history])

    def test_list_sessions_endpoint(self):
        app = build_app(FakeLlmAdapter(chunks=["ok"]))
        client = TestClient(app)
        first = client.post("/api/v1/chat", json={"prompt": "hello"})
        session_id = _extract_session_id(first.text)

        response = client.get("/api/v1/sessions")
        self.assertEqual(response.status_code, 200)
        sessions = response.json()
        self.assertTrue(any(session["id"] == session_id for session in sessions))

    def test_get_session_messages_endpoint(self):
        app = build_app(FakeLlmAdapter(chunks=["ok"]))
        client = TestClient(app)
        first = client.post("/api/v1/chat", json={"prompt": "hello"})
        session_id = _extract_session_id(first.text)

        response = client.get(f"/api/v1/sessions/{session_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["session_id"], session_id)
        messages = data["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "hello")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["payload"]["tokens"], "ok")

    def test_metrics_recorded_by_middleware_and_queried_by_tool(self):
        db = make_temp_db_manager()
        app = ChatApp.create(
            agent=build_gateway(FakeLlmAdapter()),
            event_bus=MessageEventBus(),
            db_manager=db,
        )
        client = TestClient(app)
        client.get("/api/v1/sessions")
        client.get("/api/v1/sessions")

        tool_metric_service = MetricService(db)
        tool = MetricsTool(metric_service=tool_metric_service)
        res = tool.invoke({"metric_names": ["http.requests"]})
        self.assertIn("Metric: http.requests", res)
        self.assertIn("sum=2.0000", res)




def _extract_session_id(content):
    import json

    for frame in content.split("\n\n"):
        if "event: session" not in frame:
            continue
        for line in frame.splitlines():
            if line.startswith("data:"):
                data = json.loads(line.split("data:", 1)[1].strip())
                return data["payload"]["session_id"]
    return None


async def _collect(async_iter):
    return [chunk async for chunk in async_iter]
