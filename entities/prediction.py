#!/usr/bin/env python3

from pydantic import BaseModel

from entities.asset import Asset


class Prediction(BaseModel):
    asset: Asset
    timestamp: str
    predicted_price: float
    predicted_price: float
    confidence_score: float
    model_used: str
