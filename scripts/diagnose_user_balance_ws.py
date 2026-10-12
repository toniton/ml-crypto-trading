import logging
import os
import sys
import time

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath("."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from src.exchange.managers.websocket_manager import WebSocketManager
from src.exchange.clients.cryptodotcom.cryptodotcom_websocket_service import CryptoDotComWebSocketService
from src.trading.accounts.account_manager import AccountManager
from src.trading.session.session_manager import SessionManager
from src.exchange.managers.rest_manager import RestManager
from src.events.message_event_bus import MessageEventBus, CallbackSubscription
from src.trading.events import BalanceChangedEvent
from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.timeframe import Timeframe
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum

def run_diagnostics():
    print("=" * 70)
    print("  CRYPTO.COM USER.BALANCE WEBSOCKET LIVE DIAGNOSTICS")
    print("=" * 70)

    event_bus = MessageEventBus()
    events_received = []

    def on_balance_event(event: BalanceChangedEvent):
        print(f"\n>>> [EVENT BUS NOTIFICATION] BalanceChangedEvent:")
        print(f"    Exchange:           {event.exchange}")
        print(f"    Currency:           {event.currency}")
        print(f"    Available Balance:  {event.available}")
        print(f"    Total Balance:      {event.total}")
        print(f"    Previous Available: {event.previous_available}")
        print(f"    Source:             {event.source}")
        print(f"    Version:            {event.version}\n")
        events_received.append(event)

    event_bus.subscribe(BalanceChangedEvent.__name__, CallbackSubscription(on_balance_event))

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

    from src.exchange.clients.cryptodotcom.cryptodotcom_rest_service import CryptoDotComRestService

    rest_manager = RestManager()
    rest_manager.register_service(CryptoDotComRestService())
    session_manager = SessionManager(event_bus=event_bus)
    ws_manager = WebSocketManager()
    cdc_service = CryptoDotComWebSocketService()
    ws_manager.register_service(cdc_service)

    account_manager = AccountManager(
        assets=[sample_asset],
        rest_manager=rest_manager,
        websocket_manager=ws_manager,
        session_manager=session_manager,
        event_bus=event_bus,
    )

    print("\n[Step 1] Fetching Baseline Balances via REST API...")
    try:
        baseline = account_manager.reconcile_account_balances("CRYPTO_DOT_COM")
        print(f"  Baseline balances fetched ({len(baseline)} currencies):")
        for b in baseline:
            print(f"    - {b.currency}: {b.available_balance}")
    except Exception as exc:
        print(f"  [WARN] REST balance baseline failed: {exc}")

    print("\n[Step 2] Connecting WebSocketManager...")
    ws_manager.connect()

    print("\n[Step 3] Initializing AccountManager user.balance subscription...")
    account_manager.init_websocket()

    print("\n[Step 4] Actively listening for balance changes on WebSocket stream (Press Ctrl+C to stop)...")
    sys.stdout.flush()
    start_time = time.time()
    last_log = 0.0

    try:
        while True:
            time.sleep(1)
            now = time.time()
            if now - last_log >= 5.0:
                elapsed = int(now - start_time)
                state = account_manager.get_account_state("CRYPTO_DOT_COM")
                tracked = [f"{curr}={bal.available}" for curr, bal in state.balances.items()]
                print(f"  [Monitoring t+{elapsed:03d}s] Current State: {', '.join(tracked)}")
                sys.stdout.flush()
                last_log = now
    except (KeyboardInterrupt, SystemExit):
        print("\nTermination signal received.")

    print("\n[Step 5] Final Diagnostic Summary:")
    state = account_manager.get_account_state("CRYPTO_DOT_COM")
    print(f"  Currencies in state: {len(state.balances)}")
    for curr, b in state.balances.items():
        print(f"    - {curr}: available={b.available}, total={b.total}, source={b.source}, version={b.version}")

    print(f"  Total BalanceChangedEvents triggered: {len(events_received)}")

    print("\n[Step 6] Shutting down WebSocket connection cleanly...")
    account_manager.shutdown()
    print("Diagnostics completed.\n")
    sys.stdout.flush()
    sys.exit(0)

if __name__ == "__main__":
    run_diagnostics()
