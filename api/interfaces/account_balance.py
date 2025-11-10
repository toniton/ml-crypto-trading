#!/usr/bin/env python3
from pydantic.dataclasses import dataclass


@dataclass
class AccountBalance:
    available_balance: float
    position_balance: float
