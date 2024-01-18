- https://www.quora.com/Do-stock-trading-bots-exist-If-yes-where-can-I-find-them
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