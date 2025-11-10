#!/usr/bin/env python3
from pydantic.dataclasses import dataclass


@dataclass
class Fees:
    maker_fee_pct: float
    taker_fee_pct: float
