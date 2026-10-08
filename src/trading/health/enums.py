from enum import Enum


class TradingHealthState(str, Enum):
    STARTING = "STARTING"
    SYNCING = "SYNCING"
    READY = "READY"
    TRADING = "TRADING"
    DEGRADED = "DEGRADED"
    PAUSED = "PAUSED"
    RECOVERING = "RECOVERING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


class TradingHealthCondition(str, Enum):
    EXCHANGE_UNAVAILABLE = "exchange_unavailable"
    MARKET_DATA_STALE = "market_data_stale"
    BALANCE_MISMATCH = "balance_mismatch"
    ORDER_RECONCILIATION_FAILED = "order_reconciliation_failed"
    DATABASE_UNAVAILABLE = "database_unavailable"
    RISK_LIMIT_BREACHED = "risk_limit_breached"
    CONFIG_INVALID = "config_invalid"


class ScopeType(str, Enum):
    GLOBAL = "global"
    EXCHANGE = "exchange"
    QUOTE_PORTFOLIO = "quote_portfolio"
    ASSET = "asset"


class TradingPermission(str, Enum):
    NEW_ORDERS = "new_orders"
    MODIFY_ORDERS = "modify_orders"
    CANCEL_ORDERS = "cancel_orders"
    REDUCE_POSITIONS = "reduce_positions"
    CLOSE_POSITIONS = "close_positions"
