#!/usr/bin/env python3

import yfinance as yf
import pandas as pd
import os

# ticker = "^GSPC"
# keywords = ["sp500", "S&P 500"]


class YahooFinance:
	@staticmethod
	def get_data_source(ticker: str, period: str = "5mo"):
		if os.path.exists(f"../localstorage/{ticker}-{period}.csv"):
			sp500 = pd.read_csv(f"../localstorage/{ticker}-{period}.csv", parse_dates=["Date"])
		else:
			ticker_data = yf.Ticker(ticker)
			sp500 = ticker_data.history(period=period)
			sp500.to_csv(f"../localstorage/{ticker}-{period}.csv")

		return sp500
