#!/usr/bin/env python3
import pandas as pd
from pandas import DataFrame
from pytrends.request import TrendReq


# example keywords = ["sp500", "S&P 500"]
def get_google_trends_factor(keywords: list[str]) -> DataFrame:
    request = TrendReq(hl="en-US", tz=360)
    request.build_payload(keywords, cat=0)
    trends: DataFrame = request.interest_over_time()
    trends.index = pd.to_datetime(trends.index).date
    trends["Google"] = trends.iloc[:, -3:-1].sum(axis=1)
    for word in keywords:
        del trends[word]
    del trends["isPartial"]
    return trends
