#!/usr/bin/env python3

import yfinance as yf
import pandas as pd
import os

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score


from trends import get_google_trends_factor

ticker = "^GSPC"
keywords = ["sp500", "S&P 500"]

if os.path.exists("sp500.csv"):
	sp500 = pd.read_csv("sp500.csv", index_col=1)
	sp500 = sp500.reset_index(drop=True)
else:
	sp500 = yf.Ticker(ticker)
	# TODO change 1mo to max
	sp500 = sp500.history(period="5mo")
	sp500.to_csv("sp500.csv")


#
# # Cleanup stock data
sp500["Date"] = sp500["Date"].dt.date
del sp500["Dividends"]
del sp500["Stock Splits"]
#
sp500["Tomorrow"] = sp500["Close"].shift(-1)
sp500["Target"] = (sp500["Tomorrow"] > sp500["Close"]).apply(int)

# Remove last item, since there won't be a tomorrow for it.
sp500 = sp500.drop(sp500.index[-1])

trends = get_google_trends_factor(keywords)

print(trends.to_markdown(tablefmt="grid"))
#
sp500 = sp500.join(trends)
# sp500["Google"] = sp500["Google"].fillna(0)
#

print(sp500.to_markdown(tablefmt="grid"))
# print(sp500.columns)
# print(trends.columns)
#
#
# model = RandomForestClassifier(n_estimators=200, min_samples_split=50, random_state=1)
#
# train = sp500.iloc[:-100]
# test = sp500.iloc[-100:]
#
# predictors = ["Close", "Volume", "Open", "High", "Low"]
#
# model.fit(train[predictors], train["Target"])
#
# horizons = [2, 5, 60, 250, 1000]
# new_predictors = ["Google"]
#
# for horizon in horizons:
# 	rolling_averages = sp500.rolling(horizon).mean()
#
# 	ratio_column = f"Close_Ratio_{horizon}"
# 	sp500[ratio_column] = sp500["Close"] / rolling_averages["Close"]
#
# 	trend_column = f"Trend_{horizon}"
# 	sp500[trend_column] = sp500.shift(1).rolling(horizon).sum()["Target"]
#
# 	new_predictors += [ratio_column, trend_column]
#
# sp500 = sp500.dropna(subset=sp500.columns[sp500.columns != "Tomorrow"])
# sp500.to_csv("sp500_rolling.csv")
# print(sp500)
#
# print("Predicitors [][][]")
# print(predictors)
#
#
# def predict(train, test, predictors, model):
# 	model.fit(train[predictors], train["Target"])
# 	preds = model.predict_proba(test[predictors])[:,1]
# 	preds[preds >= .6] = 1
# 	preds[preds <= .6] = 0
# 	preds = pd.Series(preds, index=test.index, name="Predictions")
# 	combined = pd.concat([test["Target"], preds], axis=1)
# 	return combined
#
#
# def backtest(data, model, predictors, start=2500, step=250):
# 	all_predictions = []
# 	for i in range(start, data.shape[0], step):
# 		train = data.iloc[0:i].copy()
# 		test = data.iloc[i:(i+step)].copy()
# 		predictions = predict(train, test, predictors, model)
# 		all_predictions.append(predictions)
# 	return pd.concat(all_predictions)
#
#
# predictions = backtest(sp500, model, predictors)
#
# predictions["Predictions"].value_counts()
#
# score = precision_score(predictions["Target"], predictions["Predictions"])
#
# print("Precision score %::::")
# print(score)
#
#
# predictions["Target"].value_counts() / predictions.shape[0]
#
# print("Predictions::::")
# print(predictions)
#
#
# new_predictions = backtest(sp500, model, new_predictors)
#
# print("New predictions >>>>")
# print(new_predictions)
#
#
# score = precision_score(new_predictions["Target"], new_predictions["Predictions"])
#
# print("Precision score %::::")
# print(score)
