#!/usr/bin/env python3
from typing import List

from pydantic import BaseModel


class NewsArticle(BaseModel):
    title: str
    source: str
    publish_date: str
    content: str
    sentiment_score: float
    assets_mentioned: List[str]
