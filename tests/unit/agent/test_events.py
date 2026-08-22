import json

from src.agent import ApprovalBlock, MarkdownBlock
from src.agent import AIEvent


class TestAIEvent:
    def test_to_dict_shape(self):
        event = AIEvent(type="node_started", response_id="abc123", payload={"node": "x"})
        data = event.to_dict()
        assert data["type"] == "node_started"
        assert data["response_id"] == "abc123"
        assert data["payload"] == {"node": "x"}

    def test_block_event_carries_id(self):
        event = AIEvent(type="block", response_id="abc", id="b3", payload=MarkdownBlock.from_text("hi"))
        data = event.to_json()
        parsed = json.loads(data)
        assert parsed["id"] == "b3"
        assert parsed["payload"]["type"] == "markdown"
        assert parsed["payload"]["content"] == "hi"

    def test_approval_payload_serializes_structured_actions(self):
        event = AIEvent(type="block", response_id="abc", id="b4", payload=ApprovalBlock.build())
        parsed = json.loads(event.to_json())
        actions = parsed["payload"]["actions"]
        assert actions == [
            {"id": "approve", "label": "Approve"},
            {"id": "reject", "label": "Reject"},
        ]

    def test_non_block_events_omit_id(self):
        event = AIEvent(type="done", response_id="abc", payload={"kind": "general"})
        assert "id" not in event.to_dict()

    def test_agent_field_included_when_set(self):
        event = AIEvent(type="node_started", response_id="abc", agent="configuration", payload={"node": "x"})
        data = event.to_dict()
        assert data["agent"] == "configuration"

    def test_agent_field_omitted_when_empty(self):
        event = AIEvent(type="node_started", response_id="abc", payload={"node": "x"})
        assert "agent" not in event.to_dict()

    def test_default_empty_fields(self):
        event = AIEvent(type="token")
        assert event.response_id == ""
        assert event.id == ""
        assert event.agent == ""

    def test_clarification_event_serializes(self):
        event = AIEvent(
            type="clarification",
            response_id="abc",
            payload={"question": "what?", "intent": "configuration"},
        )
        parsed = json.loads(event.to_json())
        assert parsed["type"] == "clarification"
        assert parsed["payload"]["question"] == "what?"
        assert parsed["payload"]["intent"] == "configuration"
