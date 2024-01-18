#!/usr/bin/env python3
from pandas import DataFrame
import pandas as pd
import os
from pathlib import Path
from pytrends.request import TrendReq


class GoogleTrends:
    def __init__(self):
        self.directory = Path(os.getcwd()).joinpath("./localstorage")
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def get_google_trends_factor(keywords: list[str]) -> DataFrame:
        request = TrendReq(hl="en-US", tz=360)
        request.build_payload(keywords, cat=0)
        trends: DataFrame = request.interest_over_time()
        trends["Date"] = pd.to_datetime(trends.index).date
        trends["Google"] = trends.iloc[:, -3:-1].sum(axis=1)
        for word in keywords:
            del trends[word]
        del trends["isPartial"]
        return trends

    def get_data_source(self, keywords: list[str]) -> DataFrame:
        file_path = f"{self.directory}/{''.join(keywords)}.csv"
        if os.path.exists(file_path):
            trends_history = pd.read_csv(file_path)
        else:
            trends_history = GoogleTrends.get_google_trends_factor(keywords)
            trends_history.to_csv(file_path)
        trends_history = trends_history.reset_index()
        return trends_history
