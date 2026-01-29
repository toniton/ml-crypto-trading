from typing import Optional

from src.configuration.environment_config import ExchangeCredentials


class CryptoDotComConfig(ExchangeCredentials):
    rest_endpoint: Optional[str] = None
    websocket_endpoint: Optional[str] = None
