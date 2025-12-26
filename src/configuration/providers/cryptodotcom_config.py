from typing import Optional
from pydantic import BaseModel


class CryptoDotComConfig(BaseModel):
    rest_endpoint: Optional[str] = None
    websocket_endpoint: Optional[str] = None
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
