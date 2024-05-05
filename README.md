# Rio Trading Bot

Rio trading bot is a free and open source crypto trading engine written in Python.

## Key concepts
### Trading context
The trading context contains market data and other information required necessary for strategies to make informed trading decisions regarding buy and sell actions.

### Consensus
The consensus model is built-in to the trading engine which enables using multiple strategies for making trade decisions. This settings allows multiple strategies to form a quorum and collectively vote through the [Byzantine Fault Tolerance](https://en.wikipedia.org/wiki/Byzantine_fault) model. 


### Strategies
These are rules that define when a trade action is performed based on the trading context, candles and other pre-configured settings.

### Prediction
The prediction engine is used to build AI/ML models, using [Random forest classifier](https://en.wikipedia.org/wiki/Random_forest) to predict if a price of an asset will either take an upward or downward trend. The built models are implemented using a Prediction strategy which gets called by the Trading engine.

### Storage
Orders are stored in MySQL database for persistence/retrieval. However, temporary data are stored within the application context and are lost when the application is stopped.

### Backtesting
The application allows a backtesting service to be register providers and strategies at runtime using a specific port.

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


******************- https://www.quora.com/Do-stock-trading-bots-exist-If-yes-where-can-I-find-them
- https://www.vestinda.com/?utm_content=q-cryptoInvesting
Buy when
Price approaches EMA of X periods and price Y periods ago was higher them EMA Y periods ago and previous tick close price was bigger than current close price

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
- TODO: Create policy config (E.g. Buy 15% < last sold price, Sell 35% > last buy price, Take 5% profit, risk 75% of pot).
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