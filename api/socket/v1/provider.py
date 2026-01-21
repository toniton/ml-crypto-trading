from pydantic.v1.dataclasses import dataclass

from src.core.managers.exchange_rest_manager import ExchangeRestManager


@dataclass(config={"arbitrary_types_allowed": True})
class ProviderSocketMessage:
    action: str
    provider: ExchangeRestManager
