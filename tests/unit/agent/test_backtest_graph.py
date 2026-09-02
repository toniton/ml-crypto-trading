from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock

from api.interfaces.backtest_request import BacktestDataSourceType
from src.agent.backtest.graph import BacktestGraph
from src.agent.backtest.models import (
    BacktestAgentRequest,
    BacktestQuality,
    BacktestTimeRange,
    BacktestValidation,
)
from src.agent.backtest.nodes.analyze_result import AnalyzeResultNode
from src.agent.backtest.nodes.build_request import BuildBacktestRequestNode
from src.agent.backtest.nodes.present_result import PresentResultNode
from src.agent.backtest.nodes.run_backtest import RunBacktestNode
from src.agent.backtest.nodes.validate_request import ValidateBacktestRequestNode

from src.agent.gateway import AgentGateway
from src.agent.router.models import AgentGoal, AgentIntent, AgentRoute
from src.backtest.domain.metrics import BacktestSummary
from tests.unit.agent.fakes import FakeLlmAdapter


def _agent_request(**overrides) -> BacktestAgentRequest:
    kwargs = {
        "ticker_symbol": "BTC_USD",
        "time_range": BacktestTimeRange(mode="relative", duration_seconds=300),
        "data_source": BacktestDataSourceType.MARKET_DATA,
        "fee_rate": 0.001,
        "slippage_ticks": 2,
        "latency_ms": 500.0,
    }
    kwargs.update(overrides)
    return BacktestAgentRequest(**kwargs)


def _summary() -> BacktestSummary:
    return BacktestSummary(
        session_id="s",
        ticker_symbol="BTC_USD",
        status="COMPLETED",
        return_pct=Decimal("1.5"),
        absolute_pnl=Decimal("10"),
        max_drawdown_pct=Decimal("2"),
        round_trips=3,
        orders_filled=5,
        orders_cancelled=1,
    )


class TestBuildBacktestRequestNode:
    def test_resolves_relative_window(self):
        node = BuildBacktestRequestNode()
        out = node({"backtest_request": _agent_request(), "request": None})
        req = out["resolved_request"]
        assert req.ticker_symbol == "BTC_USD"
        assert req.data_source.source_type == BacktestDataSourceType.MARKET_DATA
        delta = (req.end_time - req.start_time).total_seconds()
        assert delta == 300

    def test_falls_back_to_route_goal_asset(self):
        node = BuildBacktestRequestNode()
        route = AgentRoute(
            intent=AgentIntent.BACKTEST,
            goal=AgentGoal(objective="backtest", target_asset="DOGE_USD"),
        )
        out = node({
            "backtest_request": _agent_request(ticker_symbol=None),
            "request": route,
        })
        assert out["resolved_request"].ticker_symbol == "DOGE_USD"

    def test_returns_none_without_asset(self):
        node = BuildBacktestRequestNode()
        out = node({"backtest_request": _agent_request(ticker_symbol=None), "request": None})
        assert out["resolved_request"] is None

    def test_passes_execution_config(self):
        node = BuildBacktestRequestNode()
        out = node({"backtest_request": _agent_request(), "request": None})
        execution = out["resolved_request"].execution
        assert execution is not None
        assert execution.fee_rate == Decimal("0.001")
        assert execution.slippage_ticks == 2
        assert execution.latency_ms == 500.0

    def test_execution_defaults_to_default_when_missing(self):
        node = BuildBacktestRequestNode()
        out = node({
            "backtest_request": _agent_request(fee_rate=None, slippage_ticks=None, latency_ms=None),
            "request": None,
        })
        assert out["resolved_request"].execution.fee_rate == Decimal("0.001")



class TestValidateBacktestRequestNode:
    def test_valid_request(self):
        node = ValidateBacktestRequestNode()
        out = node({"backtest_request": _agent_request(), "resolved_request": Mock()})
        assert out["validation"].valid is True

    def test_missing_asset_is_invalid(self):
        node = ValidateBacktestRequestNode()
        out = node({"backtest_request": _agent_request(ticker_symbol=None), "resolved_request": None})
        validation = out["validation"]
        assert validation.valid is False
        assert any("asset" in error.lower() for error in validation.errors)

    def test_short_window_warns(self):
        node = ValidateBacktestRequestNode()
        agent_request = _agent_request(
            time_range=BacktestTimeRange(mode="relative", duration_seconds=30)
        )
        out = node({"backtest_request": agent_request, "resolved_request": Mock()})
        assert out["validation"].valid is True
        assert out["validation"].warnings

    def test_missing_execution_costs_invalid(self):
        node = ValidateBacktestRequestNode()
        agent_request = _agent_request(fee_rate=None, slippage_ticks=None, latency_ms=None)
        out = node({"backtest_request": agent_request, "resolved_request": Mock()})
        validation = out["validation"]
        assert validation.valid is False
        assert any("execution costs" in error.lower() for error in validation.errors)

    def test_missing_latency_only_invalid(self):
        node = ValidateBacktestRequestNode()
        agent_request = _agent_request(latency_ms=None)
        out = node({"backtest_request": agent_request, "resolved_request": Mock()})
        validation = out["validation"]
        assert validation.valid is False
        assert any("latency" in error.lower() for error in validation.errors)


class TestAnalyzeResultNode:
    def test_no_fills_marks_insufficient_evidence(self):
        result = Mock()
        result.fills = []
        result.market_series = list(range(5))
        out = AnalyzeResultNode()({"result": result})
        assert out["quality"].sufficient_evidence is False
        assert any("No orders" in note for note in out["quality"].notes)

    def test_missing_result(self):
        out = AnalyzeResultNode()({})
        assert out["quality"].sufficient_evidence is False


class TestRunBacktestNode:
    def test_runs_backtest_when_tool_present(self):
        service = Mock()
        result = Mock(session_id="s1")
        service.run.return_value = result
        service.summary.return_value = _summary()

        tool = Mock()
        tool.name = "run_backtest"
        tool.backtest_service = service
        llm = FakeLlmAdapter(tools=[tool])

        node = RunBacktestNode(llm)
        resolved_req = Mock()
        out = node({"resolved_request": resolved_req})

        assert out["result"] is result
        assert out["summary"].session_id == "s"
        service.run.assert_called_once_with(resolved_req)
        service.summary.assert_called_once_with("s1")

    def test_returns_error_when_tool_missing(self):
        llm = FakeLlmAdapter()
        node = RunBacktestNode(llm)
        out = node({"resolved_request": Mock()})
        assert "not available" in out["error"]

    def test_returns_error_when_service_raises(self):
        service = Mock()
        service.run.side_effect = RuntimeError("execution failed")
        tool = Mock()
        tool.name = "run_backtest"
        tool.backtest_service = service
        llm = FakeLlmAdapter(tools=[tool])

        node = RunBacktestNode(llm)
        out = node({"resolved_request": Mock()})
        assert "execution failed" in out["error"]


class TestPresentResultNode:

    def test_presents_error(self):
        out = PresentResultNode()({"error": "boom"})
        assert "Backtest failed" in out["presentation"].blocks[0].content

    def test_presents_validation_failure(self):
        out = PresentResultNode()({"validation": BacktestValidation.failed(["No asset specified."])})
        assert "No asset specified." in out["presentation"].blocks[0].content

    def test_presents_summary_and_quality(self):
        out = PresentResultNode()({
            "summary": _summary(),
            "quality": BacktestQuality(sufficient_evidence=True, notes=["few fills"]),
        })
        content = out["presentation"].blocks[0].content
        assert "BTC_USD" in content
        assert "Fills: 5" in content
        assert "few fills" in content


class TestBacktestGraph:
    def _route(self):
        return AgentRoute(
            intent=AgentIntent.BACKTEST,
            goal=AgentGoal(objective="run a backtest", target_asset="BTC_USD"),
        )

    def test_runs_end_to_end(self):
        service = Mock()
        result = Mock()
        result.session_id = "s"
        result.fills = [Mock()]
        result.market_series = list(range(30))
        service.run.return_value = result
        service.summary.return_value = _summary()

        tool = Mock()
        tool.name = "run_backtest"
        tool.backtest_service = service
        llm = FakeLlmAdapter([_agent_request()], tools=[tool])

        graph = BacktestGraph(llm).build()
        state = graph.invoke({
            "user_prompt": "run a backtest for BTC over the last 5 minutes",
            "request": self._route(),
        })

        assert state["validation"].valid is True
        assert state["summary"].ticker_symbol == "BTC_USD"
        assert state["quality"].sufficient_evidence is True
        assert "BTC_USD" in state["presentation"].blocks[0].content
        service.run.assert_called_once()
        assert llm.structured_calls[0][0] is BacktestAgentRequest

    def test_invalid_request_short_circuits_to_presentation(self):
        service = Mock()
        tool = Mock()
        tool.name = "run_backtest"
        tool.backtest_service = service
        llm = FakeLlmAdapter([_agent_request(ticker_symbol=None)], tools=[tool])

        graph = BacktestGraph(llm).build()
        state = graph.invoke({
            "user_prompt": "run a backtest",
            "request": AgentRoute(intent=AgentIntent.BACKTEST, goal=AgentGoal(objective="backtest")),
        })

        assert state["validation"].valid is False
        assert "asset" in state["presentation"].blocks[0].content.lower()
        service.run.assert_not_called()


class TestBacktestAgentRegistration:
    def test_backtest_agent_registered_with_graph(self, sample_config):
        registry = AgentGateway.build_default_registry(FakeLlmAdapter(), sample_config)
        definition = registry.get(AgentIntent.BACKTEST)
        assert definition.name == "backtest"
        assert definition.graph is not None
        assert registry.agent_name_for(AgentIntent.BACKTEST) == "backtest"




class TestBacktestRequest:
    def test_relative_time_range_defaults_to_market_data(self):
        request = BacktestAgentRequest()
        assert request.data_source == BacktestDataSourceType.MARKET_DATA
        assert request.time_range.mode == "relative"

    def test_absolute_time_range(self):
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        end = datetime.now(timezone.utc)
        request = BacktestAgentRequest(
            time_range=BacktestTimeRange(mode="absolute", start_time=start, end_time=end),
        )
        assert request.time_range.start_time == start
        assert request.time_range.end_time == end
