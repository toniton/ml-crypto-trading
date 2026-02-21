# Core Concepts

## Trading Context

The trading context contains market data and other information required necessary for strategies to make informed
trading decisions regarding buy and sell actions.

It tracks essential elements such as:

- **Balances**: Starting, available, and closing balances.
- **Trade Metrics**: Buy and sell counts, price ranges, and open/closed positions.
- **Timestamps**: Start time, end time, and last activity time for monitoring trading sessions.

## Consensus

The consensus model is built into the trading engine, enabling multiple strategies to make trade decisions cooperatively
rather than competitively. This setup allows strategies to form a quorum and collectively vote using
the [Byzantine Fault Tolerance](https://en.wikipedia.org/wiki/Byzantine_fault) approach.

### Consensus Factors

The consensus mechanism uses configurable thresholds to determine if a trade should be executed based on strategy votes.
These are defined as ratios of **True** votes (agreement) to **False** votes (disagreement).

- **Buy Consensus**: The minimum ratio required to trigger a BUY action.
- **Sell Consensus**: The minimum ratio required to trigger a SELL action.

A higher factor (e.g., 1.3) requires more agreement among strategies, while a lower factor (e.g., 0.5) is more
permissive.

## Strategies

Strategies are rules that define the decision-making of a trade action based on the trading context,
technical indicators, candle data and other pre-configured settings. Each strategy can operate independently or as part
of a multi-strategy consensus group.

## Prediction (WIP)

The trading engine can leverage machine learning models (AI/ML), such
as [Random forest classifier](https://en.wikipedia.org/wiki/Random_forest) to predict price direction (uptrend or
downtrend). Predictions are integrated into the trading workflow via a Prediction Strategy, which is invoked dynamically
by the trading engine.

> See Link - https://github.com/toniton/ml-assets-prediction

## Storage

Orders are stored in a database for persistence/retrieval. However, temporary data are stored within the application
context and are lost when the application is stopped.

## Backtesting

The application allows a backtesting service to be register providers and strategies at runtime.
It supports **multi-asset** simulation where each asset runs on an independent, concurrent clock. This allows for
realistic simulation of multiple markets simultaneously.

## Dynamic Expressions

The position sizing engine uses an expression parser that allows you to calculate trade quantities at runtime. This
provides the flexibility to define risk management and quantity logic using functional syntax directly in the YAML
configuration.

### Expression Context

A `TradingExpressionFactory` provides a rich set of variables to each expression:

| Category     | Variables                                              |
|:-------------|:-------------------------------------------------------|
| **Market**   | `close`, `high`, `low`, `volume`, `range`, `range_pct` |
| **Account**  | `balance` (quote), `equity` (total asset value)        |
| **Risk**     | `risk_pct` (default 0.01)                              |
| **Signal**   | `signal` (0.0 to 1.0 consensus score)                  |
| **Position** | `position_qty`, `avg_entry`, `pnl` (unrealized)        |
| **Metadata** | `min_qty`, `decimals`                                  |

### Technical Indicators

Common indicators are available as helper functions within expressions:

- `sma(period)`: Simple Moving Average
- `ema(period)`: Exponential Moving Average
- `rsi(period)`: Relative Strength Index
- `avg(args...)`, `min(args...)`, `max(args...)`

**Example Configuration:**

```yaml
dynamic_quantity: "(equity * 0.02) / close" # Risk 2% of total equity per trade
```
