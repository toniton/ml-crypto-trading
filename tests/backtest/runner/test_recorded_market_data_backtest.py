from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.timeframe import Timeframe
from api.interfaces.backtest_request import (
    BacktestDataSourceRequest,
    BacktestDataSourceType,
    BacktestRequest,
    ExecutionConfiguration,
)
from api.interfaces.market_data import MarketData
from src.backtest.data.backtest_data_source_resolver import BacktestDataSourceResolver
from src.backtest.runner.backtest_runner import BacktestRunner
from src.database.database_manager import DatabaseManager
from src.events.message_event_bus import MessageEventBus
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.recorder.market_data_recorder import MarketDataRecorder
from src.recorder.market_data_store import MarketDataStore
from src.trading.events import MarketDataEvent
from src.trading.strategies.strategy_registry import StrategyRegistry


def _db_manager() -> DatabaseManager:
    engine = create_engine("sqlite:///:memory:")
    DatabaseManager.BaseTableModel.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db_manager = DatabaseManager()
    db_manager.engine = engine
    db_manager._session_factory = session_factory
    return db_manager


def _asset() -> Asset:
    return Asset(
        base_ticker_symbol="BTC",
        quote_ticker_symbol="USD",
        quote_decimals=2,
        name="Bitcoin",
        exchange=ExchangeProvidersEnum.BACKTEST,
        min_quantity=0.1,
        quantity_decimals=3,
        schedule=AssetSchedule.EVERY_SECOND,
        candles_timeframe=Timeframe.MIN1,
    )


class TestRecordedMarketDataBacktest:
    def test_recorded_live_events_feed_backtest(self):
        store = MarketDataStore()
        recorder = MarketDataRecorder(store)
        bus = MessageEventBus()
        recorder.subscribe(bus)

        for timestamp, close in ((1_700_000_000.0, "100"), (1_700_001_000.0, "101"), (1_700_002_000.0, "102")):
            bus.publish(MarketDataEvent(
                ticker_symbol="BTC_USD",
                market_data=MarketData(
                    close_price=Decimal(close),
                    high_price=Decimal(close),
                    low_price=Decimal(close),
                    volume=Decimal("0"),
                    timestamp=timestamp,
                ),
            ))

        runner = BacktestRunner(
            _db_manager(),
            {"BTC_USD": _asset()},
            StrategyRegistry(),
            data_source_resolver=BacktestDataSourceResolver(store),
        )
        request = BacktestRequest(
            ticker_symbol="BTC_USD",
            data_source=BacktestDataSourceRequest(source_type=BacktestDataSourceType.MARKET_DATA),
            execution=ExecutionConfiguration(latency_ms=0.0, slippage_ticks=0, fee_rate=Decimal("0")),
        )

        result = runner.run_one(request)

        assert [data.close_price for data in result.market_series] == [
            Decimal("100"),
            Decimal("101"),
            Decimal("102"),
        ]
