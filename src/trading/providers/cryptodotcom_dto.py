from typing import Optional
from pydantic import BaseModel


class CryptoDotComRequestOrderParamsDto(BaseModel):
    instrument_name: str
    side: str
    type: str
    price: str
    quantity: str
    client_oid: Optional[str] = None
    exec_inst: Optional[list[str]] = None
    time_in_force: Optional[str] = None


class CryptoDotComBaseModel(BaseModel):
    id: int
    method: str


class CryptoDotComResponseBaseModel(CryptoDotComBaseModel):
    code: int = 0


class CryptoDotComRequestDto(BaseModel):
    id: int
    nonce: int
    method: str
    api_key: str
    sig: str


class CryptoDotComRequestOrderDto(CryptoDotComRequestDto):
    params: CryptoDotComRequestOrderParamsDto


class CryptoDotComRequestAccountBalanceDto(CryptoDotComRequestDto):
    params: object


class TickerRequestParams(BaseModel):
    channels: list[str]


class TickerRequest(BaseModel):
    id: int = 1
    method: str = "subscribe"
    params: TickerRequestParams
    nonce: int


class OrderCreated(BaseModel):
    order_id: str
    client_oid: Optional[str] = None


class CryptoDotComResponseOrderCreatedDto(CryptoDotComResponseBaseModel):
    result: OrderCreated


class OrderUpdate(OrderCreated):
    account_id: str
    order_type: Optional[str] = None
    time_in_force: Optional[str] = None
    side: Optional[str] = None
    exec_inst: list[str] = []
    quantity: Optional[str] = None
    limit_price: Optional[str] = None
    order_value: Optional[float] = None
    maker_fee_rate: Optional[float] = None
    taker_fee_rate: Optional[float] = None
    avg_price: Optional[float] = None
    cumulative_quantity: Optional[float] = None
    cumulative_value: Optional[float] = None
    cumulative_fee: Optional[float] = None
    status: Optional[str] = None
    update_user_id: Optional[str] = None
    order_date: Optional[str] = None
    instrument_name: Optional[str] = None
    fee_instrument_name: Optional[str] = None
    create_time: Optional[int] = None
    create_time_ns: Optional[int] = None
    update_time: Optional[int] = None
    transaction_time_ns: Optional[int] = None


class OrderUpdateResult(BaseModel):
    channel: Optional[str] = None
    subscription: Optional[str] = None
    data: list[OrderUpdate]
    instrument_name: Optional[str] = None


class CryptoDotComResponseOrderUpdateDto(CryptoDotComResponseBaseModel):
    result: Optional[OrderUpdateResult] = None


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
    channel: Optional[str] = None
    subscription: Optional[str] = None
    data: list[TickerData]
    instrument_name: Optional[str] = None


class CryptoDotComMarketDataResponseDto(CryptoDotComResponseBaseModel):
    result: TickerResult


class CandleData(BaseModel):
    o: str
    h: str
    l: str
    c: str
    v: str
    t: int


class CandleResult(BaseModel):
    interval: str
    data: list[CandleData]


class CryptoDotComCandleResponseDto(CryptoDotComResponseBaseModel):
    result: CandleResult


class PositionBalanceDto(BaseModel):
    instrument_name: str
    quantity: str
    market_value: str
    collateral_eligible: bool
    haircut: str
    collateral_amount: str
    max_withdrawal_balance: str
    reserved_qty: str


class UserBalanceDataDto(BaseModel):
    total_available_balance: str
    total_margin_balance: str
    total_initial_margin: str
    total_position_im: str
    total_haircut: str
    total_maintenance_margin: str
    total_position_cost: str
    total_cash_balance: str
    total_collateral_value: Optional[str] = None
    instrument_name: str
    total_session_realized_pnl: str
    total_session_unrealized_pnl: str
    is_liquidating: bool
    total_effective_leverage: str
    position_limit: str
    used_position_limit: str
    has_risk: Optional[bool] = None
    margin_score: Optional[str] = None
    credit_limits: Optional[list] = None
    terminatable: Optional[bool] = None
    total_borrow: Optional[str] = None
    total_risk_exposure: Optional[str] = None
    position_balances: list[PositionBalanceDto]


class UserBalanceResult(BaseModel):
    data: list[UserBalanceDataDto]


class CryptoDotComUserBalanceResponseDto(CryptoDotComResponseBaseModel):
    result: Optional[UserBalanceResult] = None


class UserFeesResult(BaseModel):
    spot_tier: str
    deriv_tier: str
    effective_spot_maker_rate_bps: str
    effective_spot_taker_rate_bps: str
    effective_deriv_maker_rate_bps: str
    effective_deriv_taker_rate_bps: str


class CryptoDotComUserFeesResponseDto(CryptoDotComResponseBaseModel):
    result: UserFeesResult


class InstrumentFeesResult(BaseModel):
    instrument_name: str
    effective_maker_rate_bps: str
    effective_taker_rate_bps: str


class CryptoDotComInstrumentFeesResponseDto(CryptoDotComResponseBaseModel):
    result: InstrumentFeesResult
