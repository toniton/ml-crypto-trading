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

### Quorum Mechanism & Formula

The consensus mechanism evaluates strategy votes for a given direction (`BUY` or `SELL`). Each strategy registered for that direction returns a boolean vote (`True` or `False`).

Quorum is achieved when the quorum margin is non-negative:
 
$$\text{Quorum Margin} = \text{True Count} - \text{Factor} \times (\text{Total} - \text{True Count}) \ge 0$$

Equivalently, the minimum required `true_count` is:

$$\text{True Count} \ge \frac{\text{Factor}}{1.0 + \text{Factor}} \times \text{Total}$$

- **Buy Consensus (`consensus.buy`)**: The threshold factor that must be reached for a BUY action.
- **Sell Consensus (`consensus.sell`)**: The threshold factor that must be reached for a SELL action.

### Consensus Configurations

Depending on your trading goals, you can configure the consensus engine for various operating modes:

#### 1. Single Strategy (1-of-1 Consensus)
- **Setup**: 1 strategy registered for an action with `consensus.buy: 1.0` and `consensus.sell: 1.0`.
- **Behavior**: Direct execution. When the strategy signals `True` ($1 - 1.0 \times 0 = 1 \ge 0$), quorum is met.
- **Use Case**: Simple standalone indicators or baseline strategy testing.

#### 2. Multi Strategy (1-of-2 Consensus — Trade on Each Strategy)
- **Setup**: 2 strategies registered for an action with `consensus.buy: 0.5` (or any factor $\le 1.0$) and `consensus.sell: 0.5`.
- **Behavior**: Disjunctive (OR) execution. If **either** strategy signals `True` ($1 - 0.5 \times 1 = 0.5 \ge 0$), quorum is reached.
- **Use Case**: Independent signals (e.g., trend following OR oversold dip-buying) where either condition warrants entering a position.

#### 3. Multi Strategy (2-of-2 Consensus — Trade on Quorum of Strategies)
- **Setup**: 2 strategies registered for an action with `consensus.buy: 1.3` (or any factor $> 1.0$) and `consensus.sell: 1.3`.
- **Behavior**: Conjunctive (AND) execution. A single `True` vote fails quorum ($1 - 1.3 \times 1 = -0.3 < 0$). Quorum is only reached when **both** strategies agree ($2 - 1.3 \times 0 = 2 \ge 0$).
- **Use Case**: High-conviction setups requiring confirmation across multiple uncorrelated indicators (e.g., candlestick pattern confirmed by RSI oscillator).

### Factor Quick Reference

| Strategies ($N$) | Desired Quorum | Condition | Recommended Factor Range | Example Factor |
|:-----------------|:---------------|:----------|:-------------------------|:---------------|
| 1                | 1 of 1         | $T \ge 1$ | Any factor ($0.05 - 10.0$) | `1.0`          |
| 2                | 1 of 2 (Any)   | $T \ge 1$ | $0.05 \le \text{factor} \le 1.0$ | `0.5`          |
| 2                | 2 of 2 (Quorum)| $T \ge 2$ | $1.0 < \text{factor} \le 10.0$ | `1.3`          |
| 3                | 1 of 3 (Any)   | $T \ge 1$ | $0.05 \le \text{factor} \le 0.5$ | `0.4`          |
| 3                | 2 of 3 (Majority) | $T \ge 2$ | $0.5 < \text{factor} \le 2.0$ | `1.0`          |
| 3                | 3 of 3 (Unanimous) | $T \ge 3$ | $2.0 < \text{factor} \le 10.0$ | `2.5`          |

## Strategies

Strategies are rules that define the decision-making of a trade action based on the trading context,
technical indicators, candle data and other pre-configured settings. Each strategy can operate independently or as part
of a multi-strategy consensus group.

Strategies are declared explicitly per asset in `trading-config.yaml` (see
[Asset Configuration](configuration.md)). Each entry declares how it is built (`type`:
`STATIC` built-in Python class or `DYNAMIC` expression evaluated by the `ExpressionParser`)
and the direction it votes for (`action`: `BUY`/`SELL`). A `DYNAMIC` entry can be a full
inline definition or a reference to a predefined strategy from `strategies.yaml`. Predefined
entries can describe built-in static strategies (Python `RuleBasedTradingStrategy`
subclasses such as `HammerAccumulationStrategy`) or reusable expression templates.

There are no global strategies: an asset only votes with the strategies it declares, so an
asset with an empty `strategies` list never reaches quorum. The `StrategyResolver` resolves
each asset's entries against the registry into an explicit effective set; it is pure
configuration logic and never evaluates expressions. The resolved strategies are then
instantiated as `ExpressionStrategy` (or as the referenced built-in class) and vote through
the `ConsensusManager`, which logs every strategy name and its vote for debugging.

## Prediction (WIP)

The trading engine can leverage machine learning models (AI/ML), such
as [Random forest classifier](https://en.wikipedia.org/wiki/Random_forest) to predict price direction (uptrend or
downtrend). Predictions are integrated into the trading workflow via a Prediction Strategy, which is invoked dynamically
by the trading engine.

> See Link - https://github.com/toniton/ml-assets-prediction

## Storage & Persistence

Orders, executions, and session metadata are stored in PostgreSQL for persistent analysis and historical tracking. During backtest mode, an in-memory `NoopDatabaseManager` is used to prevent test runs from polluting live database state.

## AI Agent System (LangGraph)

The bot features an autonomous AI Agent built on [LangGraph](https://github.com/langchain-ai/langgraph). The agent orchestrates specialized subgraphs to interact with traders, analyze live metrics, test strategies, and make safe configuration changes:

```
                  +-------------------------+
                  |       User Query        |
                  +------------+------------+
                               |
                               v
                  +-------------------------+
                  |      Router Graph       |
                  +---+--------+--------+---+
                      |        |        |
        +-------------+        |        +-------------+
        v                      v                      v
+---------------+      +---------------+      +---------------+
| Configuration |      |   Backtest    |      |  Performance  |
|     Graph     |      |     Graph     |      |     Graph     |
+---------------+      +---------------+      +---------------+
```

### Specialized Subgraphs

1. **Router Graph**: Classifies user intent and delegates queries to appropriate specialized subgraphs or answers directly using trading tools.
2. **Configuration Graph**:
   - Analyzes current configuration and proposed changes.
   - Generates deterministic configuration patches with mathematical validation.
   - Computes structured diffs and safety assessments.
   - Supports human-in-the-loop approval workflows (`/api/v1/proposals/...`).
3. **Backtest Graph**:
   - Parses natural language requests for backtests (e.g. "test RSI 20 buy on BTC for last week").
   - Configures simulation parameters (slippage, latency, fees).
   - Executes backtests and formats performance reports (Sharpe, Drawdown, Win Rate).
4. **Performance Analysis Graph**:
   - Queries order history, latency metrics, and daily/monthly trade heatmaps.
   - Evaluates execution quality and strategy profitability.
5. **Trading Oracle**:
   - Observes trade events and generates contextual market summaries at configured intervals.

### Agent Tool Suite

The agent interacts with the trading engine via specialized tools:
- `AccountBalanceTool`: Live quote and base currency balances.
- `PositionTool`: Open and closed position statistics.
- `GetOpenOrdersTool` & `RecentTradesTool`: Active orders and recent trade executions.
- `MetricsTool`: Process telemetry and trade latency data.
- `BacktestTool`: Programmatic historical backtesting.
- `ConsensusTool`: Current quorum factors and strategy voting status.
- `ConfigurationTool` & `VCSHistoryTool`: Inspect and modify bot configuration.

---

## High-Fidelity Backtesting

The backtesting engine allows realistic testing against historical CSV data or live audit records:

### 1. Multi-Asset Independent Clocks
Each asset runs on a virtual `BacktestClock` with concurrent stepping, accurately recreating multi-asset market dynamics.

### 2. Execution Friction Modeling
- **Latency Simulation (`--backtest-latency-ms`)**: Simulates real-world networking and exchange matching latency (e.g., 500ms).
- **Slippage Modeling (`--backtest-slippage-ticks`)**: Adjusts fill prices by configured tick increments to simulate market impact.
- **Fee Modeling (`--backtest-fee-rate`)**: Deducts realistic maker/taker fees from trade equity.

### 3. Drift Detection
The `DriftDetector` monitors performance across backtest intervals to flag strategy decay, changes in market regime, or excessive drawdown.

### 4. Deterministic Market Replay
With `MarketDataRecorder`, tick-by-tick market conditions from live sessions are saved and can be replayed identically in backtest mode.

---

## Configuration Version Control (VCS)

MCT includes a lightweight, Git-inspired Version Control System for trading configurations:

- **Immutable Snapshots**: Every committed change creates a hashed snapshot.
- **Audit Trail**: Every update records author, timestamp, commit message, and diffs.
- **Rollback & Checkout**: Restore any prior configuration state at runtime via API or Agent without application restart.

---

## Observability & Metrics Framework

MCT includes an internal metrics subsystem for real-time telemetry:

- **Runtime Metrics**: CPU and memory utilization sampled at regular intervals.
- **Order Lifecycle Metrics**: Sub-millisecond tracking of order creation, transmission, exchange acknowledgment, and execution fill times.
- **Exchange Telemetry**: REST latency, WebSocket ping/pong delays, reconnection frequency, and error rates.
- **Retention Engine**: Configurable policies to buffer and aggregate metrics for API queries and dashboard visualizations.

---

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
| **Signal**   | `signal` (+1 BUY / -1 SELL direction), `confidence` (0.0–1.0 vote ratio), plus `vote_ratio`, `weighted_vote_ratio`, `quorum_threshold`, `quorum_margin` |
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
