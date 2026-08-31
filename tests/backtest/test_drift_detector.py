from decimal import Decimal
from unittest.mock import Mock

from api.interfaces.backtest_request import BacktestDataSourceType
from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.backtest.analysis.drift_detector import BacktestDriftDetector
from src.backtest.domain.result import BacktestFill


def _fill(action: TradeAction, price: str, quantity: str) -> BacktestFill:
    return BacktestFill(
        order_uuid="o",
        ticker_symbol="BTC_USD",
        trade_action=action,
        requested_price=Decimal(price),
        market_price=Decimal(price),
        execution_price=Decimal(price),
        quantity=Decimal(quantity),
        fee=Decimal("0"),
        slippage_per_unit=Decimal("0"),
        slippage_cost=Decimal("0"),
        submitted_at=0.0,
        executed_at=0.0,
    )


def _order(action: TradeAction, price: str, quantity: str, fill_price: str | None = None) -> Order:
    return Order(
        uuid="o",
        provider_name="BACKTEST",
        ticker_symbol="BTC_USD",
        price=Decimal(price),
        quantity=quantity,
        trade_action=action,
        created_time=0.0,
        fill_price=Decimal(fill_price) if fill_price is not None else None,
    )


class TestBacktestDriftDetector:
    def test_no_drift_when_simulated_matches_live(self):
        detector = BacktestDriftDetector(Mock(), Mock())

        report = detector._compare(
            "BTC_USD",
            [_fill(TradeAction.BUY, "100", "1")],
            [_order(TradeAction.BUY, "100", "1", fill_price="100")],
        )

        assert report.drifted is False
        assert report.fill_count_drift == 0
        assert report.quantity_drift == Decimal("0")
        assert report.price_drift == Decimal("0")

    def test_fill_count_drift(self):
        detector = BacktestDriftDetector(Mock(), Mock())

        report = detector._compare(
            "BTC_USD",
            [_fill(TradeAction.BUY, "100", "1"), _fill(TradeAction.BUY, "101", "1")],
            [_order(TradeAction.BUY, "100", "1", fill_price="100")],
        )

        assert report.drifted is True
        assert report.simulated_fill_count == 2
        assert report.live_fill_count == 1
        assert report.fill_count_drift == 1

    def test_quantity_drift(self):
        detector = BacktestDriftDetector(Mock(), Mock())

        report = detector._compare(
            "BTC_USD",
            [_fill(TradeAction.BUY, "100", "1")],
            [_order(TradeAction.BUY, "100", "2", fill_price="100")],
        )

        assert report.drifted is True
        assert report.quantity_drift == Decimal("-1")

    def test_price_drift(self):
        detector = BacktestDriftDetector(Mock(), Mock())

        report = detector._compare(
            "BTC_USD",
            [_fill(TradeAction.BUY, "100", "1")],
            [_order(TradeAction.BUY, "100", "1", fill_price="105")],
        )

        assert report.drifted is True
        assert report.price_drift == Decimal("-5")

    def test_detect_replays_recorded_market_data(self):
        service = Mock()
        service.build_request.return_value = Mock()
        result = Mock()
        result.fills = [_fill(TradeAction.BUY, "100", "1")]
        service.run.return_value = result
        journal = Mock()
        journal.entries.return_value = [_order(TradeAction.BUY, "100", "1", fill_price="100")]

        detector = BacktestDriftDetector(service, journal)
        report = detector.detect("BTC_USD")

        _, kwargs = service.build_request.call_args
        assert kwargs["source_type"] == BacktestDataSourceType.MARKET_DATA
        assert report.drifted is False
