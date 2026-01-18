import threading
from api.interfaces.fees import Fees
from src.clients.rest_manager import RestManager


class FeesManager:

    def __init__(self, rest_manager: RestManager):
        self._rest_manager = rest_manager
        self.provider_fees: dict[str, Fees] = {}
        self._lock = threading.Lock()

    def init_fees(self):
        for exchange in self._rest_manager.get_registered_services():
            fees = self._rest_manager.get_account_fees(exchange)
            with self._lock:
                self.provider_fees[exchange] = fees

    def get_instrument_fees(self, provider_name: str, ticker_symbol: str) -> Fees:
        with self._lock:
            account_fees = self.provider_fees.get(provider_name)

        instrument_fees = self._rest_manager.get_instrument_fees(provider_name, ticker_symbol)

        if not account_fees:
            return instrument_fees

        return Fees(
            maker_fee_pct=min(account_fees.maker_fee_pct, instrument_fees.maker_fee_pct),
            taker_fee_pct=min(account_fees.taker_fee_pct, instrument_fees.taker_fee_pct)
        )
