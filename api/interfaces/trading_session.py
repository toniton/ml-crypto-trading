from typing import Optional
from pydantic.dataclasses import dataclass

from api.interfaces.session_time import SessionTime
from api.interfaces.trading_context import TradingContext


@dataclass
class TradingSession:
    session_id: str
    session_time: SessionTime
    trading_contexts: dict[int, TradingContext]
    commit_hash: Optional[str] = None

