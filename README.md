# Rio Trading Bot

Rio trading bot is a free and open-source cryptocurrency trading engine written in Python.
> For educational and research purposes only.

### Motivation

The intent of developing yet-another-trading-bot is to create a simple trading bot that combines engineering
expertise with financial skills within a clean, modular architecture. To enhance easy collaboration — allowing
developers and traders to integrate, experiment, and extend trading strategies with minimal complexity.

## Core concepts

### Trading context

The trading context contains market data and other information required necessary for strategies to make informed
trading decisions regarding buy and sell actions.

It tracks essential elements such as:

- Balances: Starting, available, and closing balances.
- Trade Metrics: Buy and sell counts, price ranges, and open/closed positions.
- Timestamps: Start time, end time, and last activity time for monitoring trading sessions.

### Consensus

The consensus model is built into the trading engine, enabling multiple strategies to make trade decisions cooperatively
rather than competitively. This setup allows strategies to form a quorum and collectively vote using
the [Byzantine Fault Tolerance](https://en.wikipedia.org/wiki/Byzantine_fault) approach.

### Strategies

Strategies are rules that define the decision-making of a trade action based on the trading context,
technical indicators, candle data and other pre-configured settings. Each strategy can operate independently or as part
of a multi-strategy consensus group.

### Prediction (WIP)

The trading engine can leverage machine learning models (AI/ML), such
as [Random forest classifier](https://en.wikipedia.org/wiki/Random_forest) to predict price direction (uptrend or
downtrend). Predictions are integrated into the trading workflow via a Prediction Strategy, which is invoked dynamically
by the trading engine

> See Link - https://github.com/toniton/ml-assets-prediction

### Storage

Orders are stored in MySQL database for persistence/retrieval. However, temporary data are stored within the application
context and are lost when the application is stopped.

### Backtesting

The application allows a backtesting service to be register providers and strategies at runtime using a specific port.

## Features (Currently Supported)

### Trading mode

- Spot trading

### Exchanges

- [Crypto.com](https://crypto.com/exchange)

## Architecture

```mermaid
    C4Context
    title System Context diagram for Trading System
    System_Boundary(appBoundary, "Main application") {
        System(tradingEngine, "Trading engine", "The core application that performs the trading activities.")
        System(userInterface, "Web UI", "User interface for clients to vew trading activities and graphs.")
    }
    SystemDb(database, "Database (MySQL)", "Stores all of the trades and orders, transactions, etc.")
    
    Rel(tradingEngine, database, "Writes all trading history.", "WRITE")
    Rel(userInterface, database, "Reads all trading history.", "READ")
    Rel(userInterface, tradingEngine, "Realtime get and set config at runtime.", "WEBSOCKET")


    System_Boundary(backtestBoundary, "External application") {
        System(backtestService, "Backtest service", "A registry service that configures the application for backtesting at runtime.")
    }
    
    Rel(backtestService, tradingEngine, "Register backtest providers, strategies, etc.", "WRITE")
```

## Related Projects

While this project remains focused on simplicity, learning, and experimentation, we however recommend other projects 
conceptually inspired by similar engineering and architectural ideas.

If you're interested in exploring a more advanced and production-grade trading framework, check out:
- [Nautilus Trader](https://github.com/nautechsystems/nautilus_trader) — a high-performance, event-driven algorithmic trading platform for professional and research use.


---
## Notes

******************- https://www.quora.com/Do-stock-trading-bots-exist-If-yes-where-can-I-find-them

- https://www.vestinda.com/?utm_content=q-cryptoInvesting
  Buy when
  Price approaches EMA of X periods and price Y periods ago was higher them EMA Y periods ago and previous tick close
  price was bigger than current close price

Sell when
Close price goes below EMA of X periods

Buy when
Current price is bigger than MAX price of the last 20 days

Sell when
Current price is lower than MIN price of the last 20 days

- READ: https://techspot.zzzeek.org/2012/02/07/patterns-implemented-by-sqlalchemy/

-
- TODO: Improve precision score (Fix backtesting, Add more data history).
- TODO: Create Job for state machine (Ready_to_buy, Ready_to_sell, Manual_hold).
- TODO: Create buy/sell order (using provider API such as Etrade, Binance, Crypto.com).
- TODO: Create policy config (E.g. Buy 15% < last sold price, Sell 35% > last buy price, Take 5% profit, risk 75% of
  pot).
- TODO: Make event policy (E.g. Buy 15% < last sold price, Sell 35% > last buy price).
-
-
-
- TODO: Load assets configuration
  "community_data": {
  "facebook_likes": null,
  "twitter_followers": null,
  "reddit_average_posts_48h": 0,
  "reddit_average_comments_48h": 0,
  "reddit_subscribers": null,
  "reddit_accounts_active_48h": null
  },
  "developer_data": {
  "forks": null,
  "stars": null,
  "subscribers": null,
  "total_issues": null,
  "closed_issues": null,
  "pull_requests_merged": null,
  "pull_request_contributors": null,
  "code_additions_deletions_4_weeks": {
  "additions": null,
  "deletions": null
  },
  "commit_count_4_weeks": null
  },
  "public_interest_stats": {
  "alexa_rank": null,
  "bing_matches": null
  }
- COINGECKO API has community data (useful for prediction)
- https://www.coingecko.com/api/documentation