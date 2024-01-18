from typing import Optional
from pydantic import BaseModel


class CryptoDotComRequestOrderParamsDto(BaseModel):
    instrument_name: str
    side: str
    type: str
    price: str
    quantity: str
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


class TickerRequestParams(BaseModel):
    channels: list[str]


class TickerRequest(BaseModel):
    id: int = 1
    method: str = "subscribe"
    params: TickerRequestParams
    nonce: int


class TickerData(BaseModel):
    h: Optional[str] = None
    l: Optional[str] = None
    a: Optional[str] = None
    i: str
    v: str
    vv: str
    oi: str
    c: Optional[str] = None
    b: Optional[str] = None
    bs: Optional[str] = None
    k: Optional[str] = None
    ks: Optional[str] = None
    t: int


class TickerResult(BaseModel):
    channel:  Optional[str] = None
    subscription: Optional[str] = None
    data: list[TickerData]
    instrument_name:  Optional[str] = None


class CryptoDotComMarketDataResponseDto(BaseModel):
    id: int = -1
    method: str = "subscribe"
    code: int = 0
    result: TickerResult
