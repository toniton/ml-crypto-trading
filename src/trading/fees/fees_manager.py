from api.interfaces.fees import Fees
from src.core.registries.provider_registry import ProviderRegistry


class FeesManager(ProviderRegistry):

    def __init__(self):
        super().__init__()
        self.provider_fees: dict[str, Fees] = {}

    def init_account_fees(self) -> None:
        for key, provider in self.providers.items():
            self.provider_fees[key] = provider.get_account_fees()

    def get_instrument_fees(self, ticker_symbol: str, provider_name: str) -> Fees:
        provider = self.get_provider(provider_name)
        account_fees = self.provider_fees.get(provider_name)
        instrument_fees = provider.get_instrument_fees(ticker_symbol)
        return Fees(
            maker_fee_pct=min(account_fees.maker_fee_pct, instrument_fees.maker_fee_pct),
            taker_fee_pct=min(account_fees.taker_fee_pct, instrument_fees.taker_fee_pct)
        )
