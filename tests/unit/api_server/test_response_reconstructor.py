from src.agent import ApprovalBlock, ConfigChange, MarkdownBlock
from src.agent.configuration.models import ConfigurationDiffBlock
from src.agent.events import AIEvent
from src.server.response_reconstructor import ResponseReconstructor


class TestResponseReconstructor:
    def test_token_events_are_concatenated(self):
        reconstructor = ResponseReconstructor()
        reconstructor.feed(AIEvent(type="token", payload="a"))
        reconstructor.feed(AIEvent(type="token", payload="b"))
        assert reconstructor.reconstruct() == "ab"

    def test_clarification_event_yields_question(self):
        reconstructor = ResponseReconstructor()
        reconstructor.feed(
            AIEvent(type="clarification", payload={"question": "what?", "intent": "configuration"})
        )
        assert reconstructor.reconstruct() == "what?"

    def test_clarification_event_without_question_ignored(self):
        reconstructor = ResponseReconstructor()
        reconstructor.feed(AIEvent(type="clarification", payload={"intent": "configuration"}))
        assert reconstructor.reconstruct() == ""

    def test_markdown_block_yields_content(self):
        reconstructor = ResponseReconstructor()
        reconstructor.feed(AIEvent(type="block", payload=MarkdownBlock.from_text("hello")))
        assert reconstructor.reconstruct() == "hello"

    def test_configuration_diff_block_formats_changes(self):
        reconstructor = ResponseReconstructor()
        reconstructor.feed(
            AIEvent(
                type="block",
                payload=ConfigurationDiffBlock(
                    changes=[
                        ConfigChange(
                            path="assets.BTC_USD.consensus.buy",
                            old_value=1.3,
                            new_value=1.1,
                            reason="more trades",
                        )
                    ],
                ),
            )
        )
        assert (
            reconstructor.reconstruct()
            == "Proposed changes\n- assets.BTC_USD.consensus.buy: 1.3 -> 1.1 (more trades)"
        )

    def test_approval_block_yields_message(self):
        reconstructor = ResponseReconstructor()
        reconstructor.feed(AIEvent(type="block", payload=ApprovalBlock.build()))
        assert reconstructor.reconstruct() == "Awaiting approval of the proposed configuration changes."

    def test_non_response_events_are_ignored(self):
        reconstructor = ResponseReconstructor()
        reconstructor.feed(AIEvent(type="node_started", payload={"node": "x"}))
        reconstructor.feed(AIEvent(type="node_completed", payload={"node": "x"}))
        reconstructor.feed(AIEvent(type="session", payload={"session_id": "abc"}))
        reconstructor.feed(AIEvent(type="done", payload={"kind": "general"}))
        assert reconstructor.reconstruct() == ""

    def test_reconstruct_strips_whitespace(self):
        reconstructor = ResponseReconstructor()
        reconstructor.feed(AIEvent(type="token", payload="  hi  "))
        assert reconstructor.reconstruct() == "hi"

    def test_mixed_events_reconstruct_full_response(self):
        reconstructor = ResponseReconstructor()
        reconstructor.feed(AIEvent(type="token", payload="The "))
        reconstructor.feed(AIEvent(type="block", payload=MarkdownBlock.from_text("price")))
        reconstructor.feed(AIEvent(type="token", payload=" is up."))
        assert reconstructor.reconstruct() == "The price is up."

    def test_empty_reconstruction(self):
        assert ResponseReconstructor().reconstruct() == ""
