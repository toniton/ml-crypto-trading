#!/usr/bin/env python3

from pydantic import BaseModel


class Configuration(BaseModel):
    user_id: str
    strategy_parameters: dict
    risk_tolerance: float
    cooldown_period: int
