from pydantic.v1.dataclasses import dataclass

from src.core.interfaces.exchange_rest_client import ExchangeRestClient


@dataclass(config={"arbitrary_types_allowed": True})
class ProviderSocketMessage:
    action: str
    provider: ExchangeRestClient
