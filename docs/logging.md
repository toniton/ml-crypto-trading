# Logging Architecture

The trading bot uses a mixin-based logging architecture that separates concerns, supports auditability, and provides
detailed insights into both application health and trading activity.

## Configuration

Logging is configured via `EnvironmentConfig` (Pydantic) using the following environment variables:

- `LOG_DIR`: Directory for log files. Defaults to the current directory (`.`).
- `LOG_LEVEL`: Minimum logging level (e.g., `DEBUG`, `INFO`, `WARNING`, `ERROR`).
    - **Default Behavior**:
        - `DEBUG` when `APP_ENV` is `staging`.
        - `INFO` when `APP_ENV` is `production` or other environments.

## Log Types

### 🛠 Application Logs (`application-YYYY-MM.log`)

Contains operational information for debugging and monitoring the bot's health.

- **Startup/Shutdown**: Life cycle events of the core components.
- **Configuration**: Confirmation of loaded assets and environment settings.
- **Connectivity**: WebSocket and REST API connection/reconnection events.
- **Engine Logic**: Internal consensus calculations and execution flow.
- **Errors**: Stack traces and exception details.

### 📈 Trading Logs (`trading-YYYY-MM.log`)

A high-level stream of trading events, essential for monitoring the bot's performance at a glance.

- **Order Opened**: When a buy/sell order is successfully placed (e.g., `Order opened: BTC BUY @ 42500.50`).
- **Order Closed**: When an order is filled or cancelled.
- **Execution Failures**: Specific trading-related errors.

### 📋 Audit Logs (`audit-ASSET-YYYY-MM.log`)

Partitioned by asset and saved in CSV format. These logs capture a snapshot of market conditions at the exact moment a
trade decision is made.

- **Fields**: `timestamp`, `asset`, `event_type`, `action`, `close_price`, `high_price`, `low_price`, `volume`,
  `context`.
- **Purpose**: Enables **backtest replay**, allowing you to re-run the bot against historical audit logs to analyze why
  specific decisions were made.

---

## Technical Implementation

### Mixins

Classes inherit from specific mixins to gain logging capabilities without manual logger initialization:

- `ApplicationLoggingMixin`: Provides `self.app_logger`.
- `TradingLoggingMixin`: Provides `self.trading_logger`.
- `AuditLoggingMixin`: Provides `self.log_audit_event()`.

### Example Usage

```python
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin
from src.core.logging.trading_logging_mixin import TradingLoggingMixin

class TradingExecutor(ApplicationLoggingMixin, TradingLoggingMixin):
    def execute(self, market_data):
        self.app_logger.debug("Evaluating market conditions")
        
        # ... logic ...
        
        self.trading_logger.info(f"Executing BUY for {market_data.asset}")
```

## Audit Log Replay

One of the most powerful features of the MCT bot is the ability to replay audit logs. This ensures that you are testing
your strategies with the *exact* data the bot saw when it was running live.

```bash
python main.py --assets-conf=config.yaml --backtest-mode=true --backtest-source=./logs/audit-BTC_USD-2026-01.log
```
