## High-Level Architecture

```text
+-----------------------------------------------------------------------+
|                              APPLICATION                              |
|   (Bootstrapping, Configuration, Managers, Strategies, Protections)    |
+----------------------------------+------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                            TRADING ENGINE                             |
|           (Orchestrates Scheduler and Executor interaction)           |
+------------------+-------------------------------+--------------------+
                   |                               |
                   v                               v
+-----------------------------------+   +-------------------------------+
|         TRADING SCHEDULER         |   |       TRADING EXECUTOR        |
| (Live: Time-based / Backtest: CPU)|-->| (Data -> Vote -> Risk -> Run) |
+-----------------------------------+   +---------------+---------------+
                                                        |
                                                        v
+-----------------------------------------------------------------------+
|                          MANAGER CONTAINER                            |
+-----------+-----------+-----------+-----------+-----------+-----------+
|  Market   |  Account  |   Order   | Consensus | Protection|  Session  |
|   Data    |  Manager  |  Manager  |  Manager  |  Manager  |  Manager  |
+-----------+-----------+-----+-----+-----------+-----------+-----------+
                              |
                              v
+-----------------------------------------------------------------------+
|                  REST / WEBSOCKET CLIENT REGISTRIES                   |
+--------------------------+-------------------------+------------------+
|   CryptoDotCom Client    |   Simulated Client...   |   Other Clients  |
+--------------------------+-------------------------+------------------+
```

## Core Components

The application follows a modular, manager-based architecture where responsibilities are clearly separated.

### 🚀 Application & Engine

- **Application**: The entry point/composition root. It handles the bootstrapping of configuration, database
  initialization, manager setup, and strategy/protection registration.
- **Trading Engine**: The core heart that brings together the Scheduler and Executor. It manages the starting and
  stopping of the trading lifecycle.

### ⏱️ Scheduling & Execution

- **Trading Scheduler**: Responsible for determining *when* an asset should be traded based on its configuration.
    - **LiveTradingScheduler**: Uses real-time clocks and intervals to trigger execution loops.
    - **BacktestTradingScheduler**: Driven by a `BacktestClock` to simulate time as fast as the CPU allows.
- **Trading Executor**: The core brain of the trading loop. For each scheduled tick, it:
    1. Fetches current market data via `MarketDataManager`.
    2. Gathers decision votes from all registered strategies via `ConsensusManager`.
    3. Validates the decision against risk constraints in `ProtectionManager`.
    4. Executes orders through the `OrderManager`.

### 🗃️ Managers (The Manager Layer)

- **AccountManager**: Manages exchange balances and handles balance synchronization.
- **OrderManager**: Tracks order lifecycle, maintains the `InMemoryTradingJournal`, and persists trades to the
  PostgreSQL database.
- **MarketDataManager**: Centralized source for real-time and historical price data (tickers, candles).
- **ConsensusManager**: Orchestrates the multi-strategy voting system. It ensures that trades are only executed when a
  quorum (Byzantine Fault Tolerance) is reached.
- **ProtectionManager**: Applies safety "Guards" (like `MaxDrawdownGuard`) to prevent catastrophic losses.
- **SessionManager**: Tracks the current trading session and its metadata.

### 🔌 Communication Layer

- **Client Registries**: Centralized hubs for `RestClient` and `WebSocketClient` instances.
- **Exchange Clients**: Specific implementations for different exchanges (e.g., `CryptoDotComRestClient`). These can be
  swapped with **Simulated Clients** for paper trading or backtesting.

## Configuration & System Properties

For a detailed breakdown of system properties, CLI arguments, environment variables, and asset configuration, see
the [Configuration Documentation](configuration.md).

---

## Logging Architecture

The trading bot uses a mixin-based logging architecture that separates concerns and supports auditability. For a
detailed breakdown of log types, configuration, and audit replay, see the [Logging Documentation](logging.md).
