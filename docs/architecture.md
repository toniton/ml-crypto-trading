## High-Level Architecture

```text
+---------------------------------------------------------------------------------------------------+
|                                            APPLICATION                                            |
|                  (Bootstrapping, Dependency Injection, Configuration, VCS)                         |
+-------------------+-------------------------------+-------------------------------+---------------+
                    |                               |                               |
                    v                               v                               v
+-------------------+---------------+   +-----------+-------------------+   +-----------+---------------+
|          TRADING ENGINE           |   |       AI AGENT SYSTEM         |   |    FASTAPI SERVER & WS    |
|  - Trading Scheduler (Live/Backtest)  | - LangGraph Router & Subgraphs|   | - SSE Chat Stream (/chat) |
|  - Trading Executor (Data->Vote->Risk)| - Configuration Proposal Graph|   | - Order Heatmap & Latency |
|  - Manager Container              |   | - Backtest & Analytics Graph  |   | - VCS History & Proposals |
|  - Protection Guards              |   | - Proactive Trading Oracle    |   | - WebSocket Logs (/ws)    |
+-------------------+---------------+   +-----------+-------------------+   +-----------+---------------+
                    |                               |                               |
                    +-----------------------+-------+-------------------------------+
                                            |
                                            v
+---------------------------------------------------------------------------------------------------+
|                                         MANAGER CONTAINER                                         |
+-------------------+-------------------+-------------------+-------------------+-------------------+
| MarketDataManager |  AccountManager   |   OrderManager    | ConsensusManager  | ProtectionManager |
+-------------------+-------------------+---------+---------+-------------------+-------------------+
                                                  |
                    +-----------------------------+-----------------------------+
                    |                                                           |
                    v                                                           v
+-------------------+-------------------+                   +-------------------+-------------------+
|     HIGH-FIDELITY BACKTEST ENGINE     |                   |  COMMUNICATION LAYER (REST / WS)  |
| - Virtual Concurrent BacktestClocks   |                   | - Crypto.com REST & WebSocket     |
| - Execution Frictions (Slippage/Delay)|                   | - CCXT Provider Registries        |
| - Noop Database Manager               |                   | - Simulated Paper Clients         |
| - Drift Detector & Market Recorder    |                   +-----------------------------------+
+---------------------------------------+                                       |
                    |                                                           |
                    v                                                           v
+---------------------------------------------------------------------------------------------------+
|                                     OBSERVABILITY & METRICS                                       |
| - Process Telemetry (CPU / Memory)    - Order Lifecycle Timing    - Exchange Telemetry & Errors   |
+---------------------------------------------------------------------------------------------------+
```

## Core Subsystems

The application follows a modular, decoupled architecture adhering to strict separation of concerns.

### 🚀 Application & Composition Root
- **`Application`**: Coordinates startup, configuration bootstrapping, database connections, manager instantiation, strategy registration, and graceful shutdown.
- **`VCS` (Version Control System)**: Content-addressable storage preserving snapshots of configuration changes with commit history and runtime checkout/rollback capabilities.

### ⏱️ Trading Engine
- **Trading Scheduler**: Controls asset evaluation intervals:
  - `LiveTradingScheduler`: Driven by time intervals across second, minute, hour, and daily cadences.
  - `BacktestTradingScheduler`: Driven by a virtual `BacktestClock` stepping time as fast as the CPU allows.
- **Trading Executor**: Core tick loop:
  1. Pulls candle and ticker data via `MarketDataManager`.
  2. Gathers strategy votes and determines BFT quorum via `ConsensusManager`.
  3. Evaluates position sizing via `DynamicExpressionEngine`.
  4. Validates safety constraints via `ProtectionManager`.
  5. Dispatches orders through `OrderManager`.

### 🗃️ Manager Layer
- **`AccountManager`**: Tracks multi-asset balances and synchronizes equity.
- **`OrderManager`**: Maintains order lifecycle state and persists execution journals to PostgreSQL.
- **`MarketDataManager`**: Aggregates real-time feeds, historical candle bars, and recorded market ticks.
- **`ConsensusManager`**: Evaluates multi-strategy quorum voting (1-of-1, 1-of-2 OR, 2-of-2 strict consensus).
- **`ProtectionManager`**: Enforces risk guardrails (e.g. `MaxDrawdownGuard`, cooldowns, circuit breakers).

### 🧠 AI Agent System (LangGraph)
- **`RouterGraph`**: Classifies incoming natural language queries and dynamically routes execution.
- **`ConfigurationGraph`**: Proposes strategy parameter adjustments, validates formulas, calculates diffs, and manages human-in-the-loop approvals.
- **`BacktestGraph`**: Automates on-demand historical simulations and parameter sweeps.
- **`PerformanceAnalysisGraph`**: Generates analytics on order distributions, latency, and win-rates.
- **`TradingOracle`**: Emits proactive trading and market summaries based on trade event counters.

### 📊 High-Fidelity Backtesting Subsystem
- **Multi-Asset Simulation**: Independent `BacktestClock` instances running per asset.
- **Execution Modeling**: Realistic slippage (`FixedTickSlippage`), latency delays (`FixedLatency`), and exchange fee deduction (`PercentageFee`).
- **Isolation**: Utilizes `NoopDatabaseManager` to ensure zero database side-effects during historical runs.
- **Drift Detection & Market Recording**: `DriftDetector` evaluates strategy robustness; `MarketDataRecorder` enables deterministic tick replay.

### 🌐 Server & API Layer (FastAPI)
- Exposes RESTful endpoints for configuration, VCS logs, order heatmaps, and order latency distributions.
- Streams live conversational agent turns via Server-Sent Events (`/api/v1/chat`).
- Streams real-time trading and application logs via WebSockets (`/api/v1/logs/ws`).

### 📈 Observability & Telemetry Subsystem
- **`RuntimeMetricsCollector`**: Gathers CPU and RAM utilization.
- **`OrderLifecycleCollector`**: Telemetry on order placement latency, fill delays, and slippage.
- **`ExchangeMetricsCollector`**: Monitors WebSocket connection health, REST API response times, and error rates.

---

## Configuration & Documentation Links

- [Configuration & System Properties](configuration.md)
- [Core Concepts](concepts.md)
- [Logging Architecture](logging.md)
- [Introduction & Features](introduction.md)
