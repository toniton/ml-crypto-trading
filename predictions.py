#!/usr/bin/env python3
from math import inf

import pandas as pd
from pandas import DataFrame
from sklearn.ensemble import RandomForestClassifier

from providers.google_trends import GoogleTrends
from providers.yahoo_finance import YahooFinance
from services.model_training_service import ModelTrainingService


# https://developer.etrade.com/home


def fetch_stock_data(ticker, period) -> DataFrame:
    yahoo_finance = YahooFinance()
    return yahoo_finance.get_data_source(ticker=ticker, period=period)


def preprocess_stock_data(stock_data: DataFrame) -> DataFrame:
    stock_data["YearWeek"] = pd.to_datetime(stock_data["Date"], utc=True).dt.strftime('%Y-%U')
    del stock_data["Dividends"]
    del stock_data["Stock Splits"]
    stock_data["Tomorrow"] = stock_data["Close"].shift(-1)
    stock_data["Target"] = (stock_data["Tomorrow"] > stock_data["Close"]).apply(int)
    stock_data = stock_data.drop(stock_data.index[-1])
    return stock_data


def fetch_trends_data(keywords: list[str]) -> DataFrame:
    trends = GoogleTrends()
    return trends.get_data_source(keywords)


def preprocess_trends_data(trends_data):
    trends_data["YearWeek"] = pd.to_datetime(trends_data["Date"], utc=True).dt.strftime('%Y-%U')
    return trends_data


def select_model_with_highest_precision(
        data: DataFrame,
        predictors: list[str],
        n_estimators: list[int],
        min_samples_split: list[int]
) -> tuple[RandomForestClassifier, int]:
    max_score = -inf
    best_model = None

    for estimator in n_estimators:
        for min_sample in min_samples_split:
            model_training_service = ModelTrainingService(
                n_estimators=estimator,
                min_samples_split=min_sample,
                random_state=1
            )
            model, score = model_training_service.train_model(data, predictors, (estimator - min_sample))
            max_score = max(max_score, score)
            if max_score is score:
                best_model = model
            # exit(0)

    return best_model, int(max_score)


def main():
    ticker = "^GSPC"
    keywords = ["sp500", "S&P 500"]

    historical_data = fetch_stock_data(ticker=ticker, period="10y")
    historical_data = preprocess_stock_data(historical_data)

    # print(sp500.to_markdown(tablefmt="grid"))
    # print(sp500.head())
    # try:
    #     trends = fetch_trends_data(keywords)
    #     trends = preprocess_trends_data(trends)
    # finally:
    #     pass

    # sp500 = pd.merge(sp500, trends, on=["YearWeek"], how="inner", )

    # sp500.index = pd.to_datetime(sp500["Date_x"], utc=True)
    # del sp500["Date_y"]
    # del sp500["Date_x"]
    # del sp500["YearWeek"]
    # sp500["Google"] = sp500["Google"].fillna(0)

    # Add market cap
    predictors = ["Open", "High", "Low", "Close", "Volume", ]
    n_estimators = [100]
    # n_estimators = [100, 200, 350, 400, 500, 600]
    min_samples_split = [20]
    # min_samples_split = [20, 30, 45, 50, 60, 70, 80]

    model, score = select_model_with_highest_precision(
        data=historical_data,
        predictors=predictors,
        n_estimators=n_estimators,
        min_samples_split=min_samples_split
    )

    model.apply()

    # TODO: Add Horizon to new data.
    new_data = [
        1655.25, 1659.1800537109375, 1645.8399658203125, 1646.06005859375, 92904530000,
        2655.25, 2659.1800537109375, 2645.8399658203125, 2646.06005859375,
        2655.25, 2659.1800537109375, 2645.8399658203125, 2646.06005859375,
        2655.25, 2659.1800537109375
    ]
    print("Precision:", score)
    print("Prediction :>>", model.predict([new_data]))
    print("Prediction proba:>>", model.predict_proba([new_data])[:, 1])


if __name__ == "__main__":
    main()
