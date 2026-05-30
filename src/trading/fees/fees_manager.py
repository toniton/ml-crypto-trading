from __future__ import annotations

import threading

from api.interfaces.asset import Asset
from api.interfaces.fees import Fees
from src.clients.rest_manager import RestManager


class FeesManager:

    def __init__(self, assets: list[Asset], rest_manager: RestManager):
        self.assets = assets
        self._rest_manager = rest_manager
        self.provider_fees: dict[str, Fees] = {}
        self._lock = threading.Lock()

    def init_fees(self):
        requested_exchanges = set()
        for asset in self.assets:
            exchange = asset.exchange.value
            if exchange not in requested_exchanges:
                self.get_account_fees(exchange)
                requested_exchanges.add(exchange)

    def get_account_fees(self, provider_name: str) -> Fees | None:
        account_fees = self._rest_manager.get_account_fees(provider_name)
        if account_fees is not None:
            with self._lock:
                self.provider_fees[provider_name] = account_fees
        return account_fees

    def get_instrument_fees(self, provider_name: str, ticker_symbol: str) -> Fees:
        account_fees = None
        if provider_name in self.provider_fees:
            with self._lock:
                account_fees = self.provider_fees[provider_name]

        instrument_fees = self._rest_manager.get_instrument_fees(provider_name, ticker_symbol)

        if not account_fees:
            return instrument_fees

        return Fees(
            maker_fee_pct=min(account_fees.maker_fee_pct, instrument_fees.maker_fee_pct),
            taker_fee_pct=min(account_fees.taker_fee_pct, instrument_fees.taker_fee_pct)
        )
