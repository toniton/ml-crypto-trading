#!/usr/bin/env python3

import yfinance as yf
import pandas as pd
import os

from providers.yahoo_finance import YahooFinance
from services.model_training_service import ModelTrainingService
from trends import get_google_trends_factor

ticker = "^GSPC"
keywords = ["sp500", "S&P 500"]
# https://developer.etrade.com/home
if os.path.exists("localstorage/sp500.csv"):
	sp500 = pd.read_csv("localstorage/sp500.csv", parse_dates=["Date"])
	sp500 = sp500.reset_index(drop=True)
else:
	sp500 = yf.Ticker(ticker)
	# TODO change 1mo to max
	sp500 = sp500.history(period="10y")
	sp500.to_csv("localstorage/sp500.csv")

# print(sp500["Date"].to_markdown(tablefmt="grid"))

sp500 = YahooFinance.get_data_source(ticker=ticker)

# # Cleanup stock data
sp500["YearWeek"] = pd.to_datetime(sp500["Date"], utc=True).dt.strftime('%Y-%U')
del sp500["Dividends"]
del sp500["Stock Splits"]
#
sp500["Tomorrow"] = sp500["Close"].shift(-1)
sp500["Target"] = (sp500["Tomorrow"] > sp500["Close"]).apply(int)

# Remove last item, since there won't be a tomorrow for it.
sp500 = sp500.drop(sp500.index[-1])

trends = get_google_trends_factor(keywords)
trends["YearWeek"] = pd.to_datetime(trends["Date"], utc=True).dt.strftime('%Y-%U')

sp500 = pd.merge(sp500, trends, on=["YearWeek"], how="inner", )
sp500.index = pd.to_datetime(sp500["Date_x"], utc=True)
del sp500["Date_y"]
del sp500["Date_x"]
del sp500["YearWeek"]
sp500["Google"] = sp500["Google"].fillna(0)
predictors = ["Close", "Volume", "Open", "High", "Low"]


model_training_service = ModelTrainingService(n_estimators=200, min_samples_split=50, random_state=1)
model_training_service.train_model(sp500, predictors, 150)
