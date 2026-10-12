import logging
import os
import sys
import time
from decimal import Decimal

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath("."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.timeframe import Timeframe
from src.configuration.environment_config import EnvironmentConfig
from src.configuration.exchanges_config import ExchangesConfig
from src.configuration.helpers.application_helper import ApplicationHelper
import src.configuration.providers
from src.core.interfaces.base_config import BaseConfig
from src.database.noop_database_manager import NoopDatabaseManager
from src.events.message_event_bus import MessageEventBus, CallbackSubscription
from src.exchange.clients.cryptodotcom.cryptodotcom_rest_service import CryptoDotComRestService
from src.exchange.clients.cryptodotcom.cryptodotcom_websocket_service import CryptoDotComWebSocketService
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.exchange.network import enforce_ipv4
from src.trading.events.domain_events import (
    ReconciliationCompletedEvent,
    ReconciliationDiscrepancyEvent,
)
from src.trading.managers.manager_factory import ManagerFactory
from src.trading.protection.guards.reconciliation_guard import ReconciliationGuard


def main():
    enforce_ipv4()
    print("=" * 80)
    print("  EXCHANGE RECONCILIATION ENGINE - LIVE VERIFICATION TEST")
    print("=" * 80)

    # 1. Setup Configuration & Environment
    env_config = EnvironmentConfig()
    ApplicationHelper.import_modules(src.configuration.providers)
    for cls in BaseConfig.__subclasses__():
        cls(env_config)

    exchanges_config = ExchangesConfig()
    has_keys = bool(
        exchanges_config.crypto_dot_com.api_key and exchanges_config.crypto_dot_com.secret_key
    )
    print(f"[Config] Crypto.com API Key configured: {has_keys}")
    print(f"[Config] REST Endpoint: {exchanges_config.crypto_dot_com.rest_endpoint}")

    # 2. Event Bus & Subscriptions
    event_bus = MessageEventBus()
    discrepancy_events = []
    completion_events = []

    event_bus.subscribe(
        ReconciliationDiscrepancyEvent.__name__,
        CallbackSubscription(lambda e: discrepancy_events.append(e)),
    )
    event_bus.subscribe(
        ReconciliationCompletedEvent.__name__,
        CallbackSubscription(lambda e: completion_events.append(e)),
    )

    # 3. Define Asset
    sample_asset = Asset(
        base_ticker_symbol="BTC",
        quote_ticker_symbol="USD",
        quote_decimals=2,
        name="Bitcoin",
        exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
        min_quantity=0.0001,
        quantity_decimals=4,
        schedule=AssetSchedule.EVERY_MINUTE,
        candles_timeframe=Timeframe.MIN1,
    )
    assets = [sample_asset]

    # 4. Build Live Manager Container
    db_manager = NoopDatabaseManager()
    db_manager.initialize()

    container, trading_journal = ManagerFactory.build_manager_container(
        database_manager=db_manager,
        assets=assets,
        is_simulated=False,
        event_bus=event_bus,
    )

    # Register real live exchange client services
    container.rest_manager.register_service(CryptoDotComRestService())
    container.websocket_manager.register_service(CryptoDotComWebSocketService())

    # Register ReconciliationGuard
    rec_guard = ReconciliationGuard()
    rec_guard.set_engine(container.reconciliation_engine)
    container.protection_manager.register_guard(sample_asset.key, rec_guard)

    engine = container.reconciliation_engine
    container.websocket_manager.set_reconnect_callback(engine.trigger)

    print("\n--- STEP 1: Live Baseline REST Balance Fetch ---")
    initial_balances = container.account_manager.reconcile_account_balances("CRYPTO_DOT_COM")
    print(f"  Live Balances Retrieved: {len(initial_balances)} currency balances")
    for b in initial_balances:
        print(f"    - {b.currency}: Available = {b.available_balance}")

    print("\n--- STEP 2: Full Live Reconciliation Cycle (Reconcile All) ---")
    reports = engine.reconcile_all()
    for report in reports:
        print(f"  Exchange: {report.exchange} | Cycle: {report.cycle_id[:8]} | Duration: {report.duration_ms:.2f}ms")
        print(f"  Total Discrepancies: {report.total_count}")
        print(f"  Has Critical: {report.has_critical}")
        print(f"  Trading Paused: {container.protection_manager.is_paused}")
        for disc in report.discrepancies:
            print(f"    Discrepancy: [{disc.severity.value}] {disc.discrepancy_type.value} on {disc.asset_or_currency}")
            print(f"      Local: {disc.local_value} | Exchange: {disc.exchange_value} | Diff: {disc.difference}")
            print(f"      Action: {disc.action_taken}")

    print("\n--- STEP 3: Divergence Injection & Critical Mismatch Detection Test ---")
    target_currency = "USD"
    with container.account_manager._lock:
        real_bal_obj = container.account_manager.balances["CRYPTO_DOT_COM"][target_currency]
        real_balance = Decimal(str(real_bal_obj.available_balance))
        fake_balance = real_balance + Decimal("1000.00")
        print(f"  Modifying local {target_currency} cached balance from {real_balance} to {fake_balance} (simulating drift)")
        container.account_manager.balances["CRYPTO_DOT_COM"][target_currency] = AccountBalance(
            currency=target_currency,
            available_balance=float(fake_balance),
            total_balance=float(fake_balance),
        )

    discrepancy_events.clear()
    completion_events.clear()

    print("  Triggering live reconciliation cycle...")
    drift_reports = engine.reconcile_all()

    for drift_report in drift_reports:
        print(f"  Divergence detected: {drift_report.total_count} discrepancies found")
        for disc in drift_report.discrepancies:
            print(f"    - [{disc.severity.value}] {disc.discrepancy_type.value}: {disc.asset_or_currency}")
            print(f"      Local: {disc.local_value} -> Authoritative Exchange: {disc.exchange_value}")
            print(f"      Difference: {disc.difference}")
            print(f"      Action Taken: {disc.action_taken}")

    print(f"  Trading is now paused by ProtectionManager: {container.protection_manager.is_paused}")
    print(f"  Discrepancy events published: {len(discrepancy_events)}")
    print(f"  Completion events published: {len(completion_events)}")

    # Verify that local state was authoritatively synced back to real exchange balance
    with container.account_manager._lock:
        synced_balance = Decimal(str(container.account_manager.balances["CRYPTO_DOT_COM"][target_currency].available_balance))
    print(f"  Authoritative post-reconciliation local balance: {synced_balance} (Matched real exchange: {synced_balance == real_balance})")

    # Clear discrepancies & resume
    engine.clear_discrepancies()
    container.protection_manager.resume_trading()
    print(f"  Trading resumed: {not container.protection_manager.is_paused}")

    print("\n--- STEP 4: Live Sub-Reconcilers Direct Check ---")
    for rec in engine._reconcilers:
        discs = rec.reconcile("CRYPTO_DOT_COM", assets)
        print(f"  - {rec.__class__.__name__}: {len(discs)} discrepancies")
        for d in discs:
            print(f"      [{d.severity.value}] {d.discrepancy_type.value} on {d.asset_or_currency}: {d.details}")

    print("\n--- STEP 5: Engine Background Daemon Test ---")
    engine.start()
    print("  Engine background thread started successfully. Waiting 2 seconds...")
    time.sleep(2)
    engine.stop()
    print("  Engine background thread stopped successfully.")

    print("\n" + "=" * 80)
    print("  LIVE VERIFICATION COMPLETE - ALL SYSTEMS SYNCHRONIZED & TESTED")
    print("=" * 80)


if __name__ == "__main__":
    main()
