from pydantic.dataclasses import dataclass


@dataclass
class Candle:
    open: str
    low: str
    high: str
    close: str
    start_time: float
