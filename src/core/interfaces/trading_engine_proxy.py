from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional
from pydantic import BaseModel, Field

from src.configuration.trading_config import TradingConfig
from src.recorder.market_data_store import MarketDataStore


class EngineStatus(BaseModel):
    is_running: bool = Field(description="Whether the trading engine is currently running")
    state: str = Field(default="STOPPED", description="Engine state: RUNNING, STOPPED, or PAUSED")
    monitored_assets: List[str] = Field(default_factory=list, description="List of active asset tickers")
    asset_count: int = Field(default=0, description="Total count of monitored assets")


class AssetRuntimeSnapshot(BaseModel):
    ticker_symbol: str = Field(description="Ticker symbol of the asset")
    active_strategies: List[str] = Field(default_factory=list, description="Active strategies for this asset")
    open_orders_count: int = Field(default=0, description="Count of open orders")
    total_trades_count: int = Field(default=0, description="Total executed trades count")
    position_quantity: float = Field(default=0.0, description="Current held position quantity")
    latest_price: Optional[float] = Field(default=None, description="Latest market price")


class RecordedMarketDataSummary(BaseModel):
    ticker_symbol: str = Field(description="Ticker symbol")
    observation_count: int = Field(description="Number of recorded observations")
    start_time: str = Field(description="ISO timestamp of earliest observation")
    end_time: str = Field(description="ISO timestamp of latest observation")


class TradingEngineProxy(ABC):
    """Abstract boundary into the trading engine, isolating engine internals from API consumers."""

    @abstractmethod
    def get_status(self) -> EngineStatus:
        """Returns the current runtime status and monitored assets."""

    @abstractmethod
    def list_monitored_assets(self) -> List[str]:
        """Returns the list of monitored asset tickers."""

    @abstractmethod
    def get_asset_snapshot(self, ticker_symbol: str) -> Optional[AssetRuntimeSnapshot]:
        """Returns runtime state for a specific asset ticker, if tracked."""

    @abstractmethod
    def get_recorded_market_data(self) -> List[RecordedMarketDataSummary]:
        """Returns summary of recorded market data observations."""

    @abstractmethod
    def get_market_data_store(self) -> MarketDataStore:
        """Returns the underlying market data store for data source resolution."""

    @abstractmethod
    def update_config(self, trading_config: TradingConfig) -> None:
        """Applies a configuration update to the trading engine."""

    @abstractmethod
    def compare_backtest_drift(self, action: Any) -> Any:
        """Executes backtest comparison if supported."""
