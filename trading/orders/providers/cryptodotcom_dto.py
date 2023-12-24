from typing import Optional
from pydantic import BaseModel


class CryptoDotComRequestOrderParamsDto(BaseModel):
    instrument_name: str
    side: str
    type: str
    price: float
    quantity: int
    client_oid: Optional[str] = None
    exec_inst: Optional[str] = None
    time_in_force: Optional[str] = None


class CryptoDotComResponseOrderCreatedDto(BaseModel):
    client_oid: str
    order_id: int


class CryptoDotComRequestDto(BaseModel):
    id: int
    nonce: int
    method: str
    api_key: str
    sig: str
    params: CryptoDotComRequestOrderParamsDto
