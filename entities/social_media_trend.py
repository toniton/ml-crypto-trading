#!/usr/bin/env python3

from pydantic import BaseModel

from entities.asset import Asset


class SocialMediaTrend(BaseModel):
    platform: str
    asset: Asset
    year_week: str
    sentiment_score: float
    tweet_count: int
    trend_score: float
