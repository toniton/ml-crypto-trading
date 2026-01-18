import threading
import time
from collections import defaultdict
from decimal import Decimal

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.core.registries.asset_schedule_registry import AssetScheduleRegistry
from src.clients.rest_manager import RestManager
from src.clients.websocket_manager import WebSocketManager
from src.trading.session.session_manager import SessionManager


class AccountManager(ApplicationLoggingMixin):

    def __init__(self, assets: list[Asset], rest_manager: RestManager, websocket_manager: WebSocketManager):
        self.assets = assets
        self._rest_manager = rest_manager
        self._websocket_manager = websocket_manager
        self.balances: dict[str, dict[str, AccountBalance]] = {}
        self.last_balance_updates: dict[str, dict[str, float]] = defaultdict(dict)
        self._lock = threading.Lock()

    def _cache_balances(self, provider_name: str, balances: list[AccountBalance]) -> None:
        with self._lock:
            if provider_name not in self.balances:
                self.balances[provider_name] = {}

            for balance in balances:
                self.balances[provider_name][balance.currency] = balance
                self.last_balance_updates[provider_name][balance.currency] = time.time()

        self.app_logger.debug(f"Updated balances for {provider_name}: {self.balances[provider_name]}")

    def init_websocket(self):
        for provider_name in self._websocket_manager.get_registered_services():
            self._websocket_manager.subscribe_account_balance(
                exchange=provider_name,
                callback=lambda data, provider=provider_name: self._cache_balances(provider, data)
            )

    def shutdown(self):
        for provider_name in self._websocket_manager.get_registered_services():
            self._websocket_manager.unsubscribe_account_balance(exchange=provider_name)

    def init_account_balances(self, session_manager: SessionManager):
        for asset in self.assets:
            exchange = asset.exchange
            try:
                opening_balance = self.get_quote_balance(asset, exchange.value)
                session_manager.init_asset_balance(asset, opening_balance.available_balance)
            except Exception:
                self.app_logger.error(f"Unable to initialize account balance for {asset} from {exchange}",
                                      exc_info=True)

    def get_base_balance(self, asset: Asset, provider_name: str) -> AccountBalance:
        currency_symbol = asset.base_ticker_symbol
        return self._get_balance(currency_symbol, asset.schedule, provider_name)

    def get_quote_balance(self, asset: Asset, provider_name: str) -> AccountBalance:
        currency_symbol = asset.quote_ticker_symbol
        return self._get_balance(currency_symbol, asset.schedule, provider_name)

    def _get_balance(self, currency_symbol: str, schedule: AssetSchedule, provider_name: str) -> AccountBalance:
        with self._lock:
            last_update = self.last_balance_updates.get(provider_name, {}).get(currency_symbol)
            should_refresh = (
                    last_update is None or
                    (time.time() - last_update) > AssetScheduleRegistry.UNIT_SECONDS[schedule]
            )

        if should_refresh:
            data = self._rest_manager.get_account_balance(provider_name)
            self._cache_balances(provider_name, data)

        with self._lock:
            return self.balances.get(provider_name, {}).get(currency_symbol) or AccountBalance(currency_symbol,
                                                                                               Decimal(0))

    def close_account_balances(self, session_manager: SessionManager):
        for asset in self.assets:
            exchange = asset.exchange
            try:
                closing_balance = self.get_quote_balance(asset, exchange.value)
                session_manager.close_asset_balance(asset.key, closing_balance.available_balance)
            except Exception:
                self.app_logger.error(f"Unable to close account balance for {asset} from {exchange}",
                                      exc_info=True)
