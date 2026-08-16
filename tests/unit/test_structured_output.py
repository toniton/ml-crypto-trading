import unittest
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from src.llm.base_langchain_adapter import BaseLangChainAdapter
from src.agent.configuration import ConfigurationProposal


class StubAdapter(BaseLangChainAdapter):
    """Minimal concrete adapter with an injectable underlying model."""

    def __init__(self, model):
        super().__init__()
        self._model = model


class TestGenerateStructuredFallback(unittest.TestCase):
    def test_function_calling_preferred_over_json_schema(self):
        model = MagicMock()

        def wso(schema, method="function_calling"):
            if method == "json_schema":
                raise ValueError("This model does not support response format json_schema")
            structured = MagicMock()
            structured.invoke.return_value = ConfigurationProposal(summary="ok", changes=[])
            return structured

        model.with_structured_output.side_effect = wso

        adapter = StubAdapter(model)
        result = adapter.generate_structured(ConfigurationProposal, "lower threshold", "sys")

        self.assertEqual(result.summary, "ok")
        self.assertEqual(
            model.with_structured_output.call_args_list[0].kwargs["method"],
            "function_calling",
        )

    def test_json_schema_used_when_function_calling_unavailable(self):
        model = MagicMock()

        def wso(schema, method="function_calling"):
            if method == "function_calling":
                raise NotImplementedError("tools not supported")
            structured = MagicMock()
            structured.invoke.return_value = {"summary": "schema path", "changes": []}
            return structured

        model.with_structured_output.side_effect = wso

        adapter = StubAdapter(model)
        result = adapter.generate_structured(ConfigurationProposal, "lower threshold", "sys")

        self.assertEqual(result.summary, "schema path")
        self.assertEqual(
            model.with_structured_output.call_args_list[1].kwargs["method"],
            "json_schema",
        )

    def test_json_mode_returning_dict_is_coerced(self):
        model = MagicMock()

        def wso(schema, method="function_calling"):
            structured = MagicMock()
            structured.invoke.return_value = {"summary": "dict path", "changes": []}
            return structured

        model.with_structured_output.side_effect = wso

        adapter = StubAdapter(model)
        result = adapter.generate_structured(ConfigurationProposal, "x", "sys")

        self.assertEqual(result.summary, "dict path")

    def test_all_methods_fail_then_json_instruct_fallback(self):
        model = MagicMock()
        model.with_structured_output.side_effect = ValueError("never supported")
        model.invoke.return_value = AIMessage(
            content='{"summary":"json fallback","changes":[],"risks":[],"expected_effect":""}'
        )

        adapter = StubAdapter(model)
        result = adapter.generate_structured(ConfigurationProposal, "x", "sys")

        self.assertEqual(result.summary, "json fallback")
        model.invoke.assert_called_once()

    def test_all_fallbacks_fail_raises_value_error(self):
        model = MagicMock()
        model.with_structured_output.side_effect = ValueError("never supported")
        model.invoke.side_effect = ValueError("outage")

        adapter = StubAdapter(model)
        with self.assertRaises(ValueError):
            adapter.generate_structured(ConfigurationProposal, "x", "sys")


if __name__ == "__main__":
    unittest.main()