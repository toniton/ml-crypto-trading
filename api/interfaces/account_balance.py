#!/usr/bin/env python3
from pydantic.dataclasses import dataclass


@dataclass
class AccountBalance:
    currency: str
    available_balance: float
