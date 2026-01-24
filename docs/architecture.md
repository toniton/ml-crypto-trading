# Architecture

## System Context

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

    Rel(backtestService, tradingEngine, "Register backtest schedules, strategies, etc.", "WRITE")
```

## Configuration & System Properties

For a detailed breakdown of system properties, CLI arguments, environment variables, and asset configuration, see
the [Configuration Documentation](configuration.md).

---

## Logging Architecture

The trading bot uses a mixin-based logging architecture that separates concerns and supports auditability. For a
detailed breakdown of log types, configuration, and audit replay, see the [Logging Documentation](logging.md).
