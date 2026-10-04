import unittest
from datetime import datetime, timezone

from src.llm.tools.trading_health_tool import TradingHealthTool
from src.trading.health import (
    HealthMonitor,
    HealthObservation,
    HealthScope,
    TradingHealthCondition,
    TradingHealthState,
)


class TestTradingHealthTool(unittest.TestCase):
    def setUp(self):
        self.health_monitor = HealthMonitor(initial_state=TradingHealthState.TRADING)
        self.tool = TradingHealthTool(health_monitor=self.health_monitor)

    def test_run_healthy_state(self):
        result = self.tool._run()
        self.assertIn("Trading Health State: TRADING", result)
        self.assertIn("Active Health Conditions: None", result)
        self.assertIn("new_orders", result)

    def test_run_recovering_state(self):
        self.health_monitor.set_state(TradingHealthState.PAUSED)
        self.health_monitor.set_state(TradingHealthState.RECOVERING)

        result = self.tool._run()
        self.assertIn("Trading Health State: RECOVERING", result)
        self.assertIn("State Context: Engine is in RECOVERING", result)

    def test_run_with_active_conditions(self):
        now = datetime.now(timezone.utc)
        self.health_monitor.report_observation(
            HealthObservation(
                source="market_feed",
                condition=TradingHealthCondition.MARKET_DATA_STALE,
                scope=HealthScope.asset_scope("BTC_USD"),
                healthy=False,
                observed_at=now,
                measured_value=15.2,
                threshold=10.0,
            )
        )

        result = self.tool._run()
        self.assertIn("Trading Health State: DEGRADED", result)
        self.assertIn("market_data_stale", result)
        self.assertIn("Measured: 15.2", result)
        self.assertIn("Limit: 10.0", result)
        self.assertIn("ASSET:BTC_USD", result)

    def test_run_filtered_by_scope(self):
        now = datetime.now(timezone.utc)
        self.health_monitor.report_observation(
            HealthObservation(
                source="market_feed",
                condition=TradingHealthCondition.MARKET_DATA_STALE,
                scope=HealthScope.asset_scope("BTC_USD"),
                healthy=False,
                observed_at=now,
            )
        )

        # Matching filter
        res_match = self.tool._run(scope_type="asset", scope_identifier="BTC_USD")
        self.assertIn("market_data_stale", res_match)

        # Non-matching filter
        res_no_match = self.tool._run(scope_type="asset", scope_identifier="ETH_USD")
        self.assertIn("Active Health Conditions: None", res_no_match)
