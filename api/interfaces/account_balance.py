#!/usr/bin/env python3
from decimal import Decimal

from pydantic.dataclasses import dataclass


@dataclass
class AccountBalance:
    currency: str
    available_balance: Decimal
