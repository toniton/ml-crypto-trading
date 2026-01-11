#!/usr/bin/env python3
from decimal import Decimal

from pydantic.dataclasses import dataclass


@dataclass
class Fees:
    maker_fee_pct: Decimal
    taker_fee_pct: Decimal
