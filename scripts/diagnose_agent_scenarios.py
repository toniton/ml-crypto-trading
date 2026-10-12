from __future__ import annotations

import os
import tempfile
import time
from decimal import Decimal
from typing import Optional

from fastapi.testclient import TestClient

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.agent import AgentGateway
from src.agent.actions import (
    AgentActionExecutor,
    AgentActionService,
    AgentApprovalService,
)
from src.agent.automation import AutomationController, InvestigateActivityAnomaly
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.monitoring.starvation_watchdog import StarvationWatchdog
from src.events.message_event_bus import MessageEventBus
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.recorder.market_data_store import MarketDataStore
from src.server.app import ChatApp
from src.trading.activity.asset_activity_tracker import AssetActivityTracker
from src.trading.events import (
    MarketDataEvent,
    OrderFilledEvent,
    OrderSubmittedEvent,
    SignalGeneratedEvent,
    StrategyEvaluatedEvent,
)
from src.vcs.application.service import VCSService
from tests.unit.agent.fakes import FakeLlmAdapter
from tests.unit.api_server.helpers import make_db_manager


def _build_asset(symbol: str, schedule: AssetSchedule = AssetSchedule.EVERY_MINUTE) -> Asset:
    return Asset(
        base_ticker_symbol=symbol,
        quote_ticker_symbol="USD",
        quote_decimals=2,
        name=symbol,
        exchange=ExchangeProvidersEnum.BACKTEST,
        min_quantity=0.001,
        quantity_decimals=3,
        schedule=schedule,
        candles_timeframe=Timeframe.MIN1,
        enabled=True,
    )


def wait_for(predicate, timeout: float = 4.0, description: str = "condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        val = predicate()
        if val:
            return val
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for {description}")


def main():
    print("=" * 78)
    print("  AUTONOMOUS AGENT & TRADING STARVATION DIAGNOSTIC SUITE")
    print("=" * 78)

    # 1. Setup in-memory environment
    tmp_file = os.path.join(tempfile.mkdtemp(), "diagnostic.db")
    db = make_db_manager(tmp_file)
    vcs = VCSService(db)
    seed_config = {
        "assets": [
            {
                "base_ticker_symbol": sym,
                "quote_ticker_symbol": "USD",
                "name": sym,
                "exchange": "BACKTEST",
                "min_quantity": 0.001,
                "quote_decimals": 2,
                "quantity_decimals": 3,
                "schedule": 1,
                "candles_timeframe": "MIN1",
                "enabled": True,
            }
            for sym in ("BTC", "CRO", "DOGE", "ETH", "SOL", "AVAX")
        ]
    }
    vcs.seed_if_empty(seed_config, author="init", message="Initial seed")

    bus = MessageEventBus()
    tracker = AssetActivityTracker()
    tracker.subscribe(bus)

    config_service = ConfigurationService(vcs=vcs)
    action_service = AgentActionService(event_bus=bus)
    approval_service = AgentApprovalService(
        vcs=vcs,
        configuration_service=config_service,
        action_service=action_service,
        event_bus=bus,
    )
    executor = AgentActionExecutor(
        action_service=action_service,
        approval_service=approval_service,
        vcs=vcs,
        configuration_service=config_service,
    )

    assets = [
        _build_asset("BTC", AssetSchedule.EVERY_MINUTE),      # Healthy (240s threshold)
        _build_asset("CRO", AssetSchedule.EVERY_SECOND),      # Stalled Data (63s threshold)
        _build_asset("DOGE", AssetSchedule.EVERY_MINUTE),     # Stalled Strategy (240s threshold)
        _build_asset("ETH", AssetSchedule.EVERY_MINUTE),      # Stalled Signals (240s threshold)
        _build_asset("SOL", AssetSchedule.EVERY_MINUTE),      # Stalled Orders (240s threshold)
        _build_asset("AVAX", AssetSchedule.EVERY_MINUTE),     # Stalled Execution (240s threshold)
    ]

    investigation = InvestigateActivityAnomaly(activity_provider=tracker)
    watchdog = StarvationWatchdog(
        activity_provider=tracker,
        assets=assets,
        event_bus=bus,
        poll_interval_seconds=30.0,
    )
    controller = AutomationController(
        event_bus=bus,
        executor=executor,
        approval_service=approval_service,
        investigation=investigation,
        watchdog=watchdog,
    )
    controller.start()

    gateway = AgentGateway(FakeLlmAdapter([]), vcs=vcs)
    app = ChatApp.create(
        agent=gateway,
        event_bus=bus,
        db_manager=db,
        market_data_store=MarketDataStore(),
        vcs=vcs,
    )
    client = TestClient(app)

    now = time.time()
    t_past_cro = now - 100.0   # > 63s threshold
    t_past_1m = now - 350.0    # > 240s threshold
    tracker._started_at = t_past_1m
    watchdog._started_at = t_past_1m

    def _make_order(symbol: str, created: float, executed: Optional[float] = None) -> Order:
        return Order(
            uuid=f"order-{symbol}-{int(created)}",
            provider_name="BACKTEST",
            ticker_symbol=symbol,
            price=Decimal("100"),
            quantity="1",
            trade_action=TradeAction.BUY,
            created_time=created,
            executed_time=executed,
            status=OrderStatus.COMPLETED if executed else OrderStatus.PENDING,
        )

    print("\n--- [Scenario 1] Healthy Asset Pipeline (BTC_USD) ---")
    bus.publish(MarketDataEvent(
        ticker_symbol="BTC_USD",
        market_data=MarketData(volume=Decimal("1"), high_price=Decimal("2"), low_price=Decimal("1"), close_price=Decimal("1.5"), timestamp=now),
    ))
    bus.publish(StrategyEvaluatedEvent(symbol="BTC_USD", evaluated_at=now))
    bus.publish(SignalGeneratedEvent(symbol="BTC_USD", action="BUY", generated_at=now))
    bus.publish(OrderSubmittedEvent(symbol="BTC_USD", order=_make_order("BTC_USD", now)))
    bus.publish(OrderFilledEvent(symbol="BTC_USD", order=_make_order("BTC_USD", now, executed=now)))
    print("  -> BTC_USD: All stages updated at t=now. Classification:", watchdog._classify(tracker.state_for("BTC_USD"), now, 240.0, baseline=t_past_1m))
    assert watchdog._classify(tracker.state_for("BTC_USD"), now, 240.0, baseline=t_past_1m) is None

    print("\n--- [Scenario 2] Market Data Feed Stall (CRO_USD) ---")
    # CRO last market data was 100s ago (> 63s threshold)
    bus.publish(MarketDataEvent(
        ticker_symbol="CRO_USD",
        market_data=MarketData(volume=Decimal("10"), high_price=Decimal("0.1"), low_price=Decimal("0.09"), close_price=Decimal("0.095"), timestamp=t_past_cro),
    ))
    cro_class = watchdog._classify(tracker.state_for("CRO_USD"), now, 63.0, baseline=t_past_cro)
    print(f"  -> CRO_USD Anomaly: {cro_class}")
    assert cro_class == "NO_MARKET_DATA"

    print("\n--- [Scenario 3] Strategy Evaluation Failure (DOGE_USD) ---")
    # Market data is fresh, but no strategy evaluations for 350s
    bus.publish(MarketDataEvent(
        ticker_symbol="DOGE_USD",
        market_data=MarketData(volume=Decimal("100"), high_price=Decimal("0.2"), low_price=Decimal("0.19"), close_price=Decimal("0.195"), timestamp=now),
    ))
    bus.publish(StrategyEvaluatedEvent(symbol="DOGE_USD", evaluated_at=t_past_1m))
    doge_class = watchdog._classify(tracker.state_for("DOGE_USD"), now, 240.0, baseline=t_past_1m)
    print(f"  -> DOGE_USD Anomaly: {doge_class}")
    assert doge_class == "NO_STRATEGY_ACTIVITY"

    print("\n--- [Scenario 4] Strategy Quorum Silence (ETH_USD) ---")
    # Market data and evaluation fresh, but zero signals generated for 350s
    bus.publish(MarketDataEvent(
        ticker_symbol="ETH_USD",
        market_data=MarketData(volume=Decimal("5"), high_price=Decimal("3000"), low_price=Decimal("2900"), close_price=Decimal("2950"), timestamp=now),
    ))
    bus.publish(StrategyEvaluatedEvent(symbol="ETH_USD", evaluated_at=now))
    eth_class = watchdog._classify(tracker.state_for("ETH_USD"), now, 240.0, baseline=t_past_1m)
    print(f"  -> ETH_USD Anomaly: {eth_class}")
    assert eth_class == "NO_SIGNALS"

    print("\n--- [Scenario 5] Risk / Order Gating Anomaly (SOL_USD) ---")
    # Market data, evaluation, and signals fresh, but no orders submitted
    bus.publish(MarketDataEvent(
        ticker_symbol="SOL_USD",
        market_data=MarketData(volume=Decimal("20"), high_price=Decimal("150"), low_price=Decimal("145"), close_price=Decimal("148"), timestamp=now),
    ))
    bus.publish(StrategyEvaluatedEvent(symbol="SOL_USD", evaluated_at=now))
    bus.publish(SignalGeneratedEvent(symbol="SOL_USD", action="BUY", generated_at=now))
    sol_class = watchdog._classify(tracker.state_for("SOL_USD"), now, 240.0, baseline=t_past_1m)
    print(f"  -> SOL_USD Anomaly: {sol_class}")
    assert sol_class == "NO_ORDERS"

    print("\n--- [Scenario 6] Exchange Execution Stall (AVAX_USD) ---")
    # Orders submitted, but no fills executed for 350s
    bus.publish(MarketDataEvent(
        ticker_symbol="AVAX_USD",
        market_data=MarketData(volume=Decimal("30"), high_price=Decimal("35"), low_price=Decimal("33"), close_price=Decimal("34"), timestamp=now),
    ))
    bus.publish(StrategyEvaluatedEvent(symbol="AVAX_USD", evaluated_at=now))
    bus.publish(SignalGeneratedEvent(symbol="AVAX_USD", action="BUY", generated_at=now))
    bus.publish(OrderSubmittedEvent(symbol="AVAX_USD", order=_make_order("AVAX_USD", now)))
    bus.publish(OrderFilledEvent(symbol="AVAX_USD", order=_make_order("AVAX_USD", t_past_1m, executed=t_past_1m)))
    avax_class = watchdog._classify(tracker.state_for("AVAX_USD"), now, 240.0, baseline=t_past_1m)
    print(f"  -> AVAX_USD Anomaly: {avax_class}")
    assert avax_class == "NO_EXECUTIONS"

    print("\n--- [Scenario 7] Watchdog Run & End-to-End Autonomous Reaction ---")
    # Execute watchdog poll
    emitted = watchdog.run_once()
    print(f"  Emitted Anomalies Count: {len(emitted)}")
    for ev in emitted:
        print(f"    - Asset: {ev.asset:<10} Kind: {ev.anomaly_kind:<22} Threshold: {ev.threshold}s")

    # Wait for actions and approvals to project via async worker
    wait_for(lambda: client.get("/api/v1/agent/actions").json(), description="Actions projection")
    actions = client.get("/api/v1/agent/actions").json()
    print(f"\n  Projected Actions ({len(actions)}):")
    for act in actions:
        print(f"    [{act.get('type')}] {act.get('title')} -> status={act.get('status')}")

    # For SOL_USD (NO_ORDERS), an approval proposal to pause the asset should be pending
    wait_for(lambda: client.get("/api/v1/agent/approvals").json(), description="Approval proposal")
    approvals = client.get("/api/v1/agent/approvals").json()
    print(f"\n  Projected Approvals ({len(approvals)}):")
    for apprv in approvals:
        print(f"    [{apprv.get('status')}] {apprv.get('title')} (id={apprv.get('id')})")

    # Decide approve on the proposal
    sol_approval = next(a for a in approvals if "SOL_USD" in a.get("title", "") or a.get("asset") == "SOL_USD")
    apprv_id = sol_approval["id"]
    print(f"\n  Approving Proposal {apprv_id}...")
    res = client.post(f"/api/v1/agent/approvals/{apprv_id}/decision", json={"action": "approve"})
    assert res.status_code == 202
    wait_for(
        lambda: any(a["id"] == apprv_id and a["status"] == "APPROVED" for a in client.get("/api/v1/agent/approvals").json()),
        description="Approval execution",
    )
    print("  -> Proposal APPROVED and committed to VCS!")
    head = vcs.head("HEAD")
    print(f"  -> New VCS HEAD: {head.hash[:8]} by {head.author}")

    # Check conversation sessions and message contents
    sessions = client.get("/api/v1/sessions").json()
    print(f"\n  Projected Chat Sessions ({len(sessions)}):")
    for s in sessions:
        msgs = client.get(f"/api/v1/sessions/{s['id']}").json()["messages"]
        print(f"    Session {s['id']}: {len(msgs)} messages")
        for m in msgs:
            print(f"      [{m['role']}] {m['content'][:80]}...")

    print("\n--- [Scenario 8] Starvation Recovery / Clearance ---")
    # Resume fresh market data, evaluations, signals, orders, executions for CRO
    now_rec = time.time()
    bus.publish(MarketDataEvent(
        ticker_symbol="CRO_USD",
        market_data=MarketData(volume=Decimal("10"), high_price=Decimal("0.1"), low_price=Decimal("0.09"), close_price=Decimal("0.095"), timestamp=now_rec),
    ))
    bus.publish(StrategyEvaluatedEvent(symbol="CRO_USD", evaluated_at=now_rec))
    bus.publish(SignalGeneratedEvent(symbol="CRO_USD", action="BUY", generated_at=now_rec))
    bus.publish(OrderSubmittedEvent(symbol="CRO_USD", order=_make_order("CRO_USD", now_rec)))
    bus.publish(OrderFilledEvent(symbol="CRO_USD", order=_make_order("CRO_USD", now_rec, executed=now_rec)))

    # Watchdog poll should now clear CRO from triggered set and emit no anomaly for CRO
    emitted_after_recovery = watchdog.run_once()
    assert not any(e.asset == "CRO_USD" for e in emitted_after_recovery)
    assert "CRO_USD" not in watchdog._triggered
    print("  -> CRO_USD activity resumed: watchdog triggered state cleared successfully!")

    controller.stop()
    print("\n" + "=" * 78)
    print("  ALL 8 DIAGNOSTIC SCENARIOS PASSED PERFECTLY!")
    print("=" * 78)


if __name__ == "__main__":
    main()
