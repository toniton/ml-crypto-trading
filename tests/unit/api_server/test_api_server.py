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
from src.agent.router.models import AgentGoal, AgentIntent, AgentRoute
from src.server.app import ChatApp
from src.server.server import ApiServer
from tests.unit.agent.fakes import FakeLlmAdapter

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


class TestApiServerApp(unittest.TestCase):
    def setUp(self):
        self.llm = FakeLlmAdapter(chunks=["Token1 ", "Token2 ", "Token3"])
        self.app = ChatApp.create(agent=build_gateway(self.llm))
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
        app_no_agent = ChatApp.create(agent=None)
        client = TestClient(app_no_agent)
        response = client.post("/api/v1/chat", json={"prompt": "Hello"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("Agent is not configured.", response.json()["detail"])

    @patch("uvicorn.Server.run")
    def test_api_server_lifecycle(self, mock_uvicorn_run):
        server = ApiServer(agent=build_gateway(self.llm), host="127.0.0.1", port=9999)
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
                changes=[ConfigChange(path="consensus.buy", old_value=1.3, new_value=1.1, reason="more trades")],
            ),
        ])
        app = ChatApp.create(agent=build_gateway(llm))
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
        # response_id correlated on every event
        response_ids = {data["response_id"] for _, data in events}
        self.assertEqual(len(response_ids), 1)
        self.assertTrue(len(response_ids.pop()) == 32)
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
                changes=[ConfigChange(path="consensus.buy", old_value=1.3, new_value=1.1, reason="more trades")],
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
        self.assertEqual(diff_block.changes[0].path, "consensus.buy")


async def _collect(async_iter):
    return [chunk async for chunk in async_iter]


if __name__ == "__main__":
    unittest.main()