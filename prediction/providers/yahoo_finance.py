#!/usr/bin/env python3

import yfinance as yf
import pandas as pd
import os
from pathlib import Path


class YahooFinance:
	def __init__(self):
		self.directory = Path(os.getcwd()).joinpath("./localstorage")
		self.directory.mkdir(parents=True, exist_ok=True)

	def get_data_source(self, ticker: str, period: str = "5y"):
		file_path = f"{self.directory}/{ticker}-{period}.csv"
		if os.path.exists(file_path):
			asset_history = pd.read_csv(file_path)
		else:
			ticker_data = yf.Ticker(ticker)
			asset_history = ticker_data.history(period=period)
			asset_history.to_csv(file_path)

		asset_history = asset_history.reset_index()
		return asset_history
