from decimal import Decimal
from unittest.mock import Mock

from api.interfaces.backtest_request import BacktestDataSourceType
from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.backtest.analysis.drift_detector import BacktestDriftDetector
from src.backtest.domain.result import BacktestFill, PortfolioSnapshot


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
        commit_hash="56339b9",
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

    def test_detect_populates_simulated_equity_curve_from_portfolio_snapshots(self):
        service = Mock()
        service.build_request.return_value = Mock()
        result = Mock()
        result.fills = [_fill(TradeAction.BUY, "100", "1")]
        result.initial_balance = Decimal("10000")
        result.portfolio_snapshots = [
            PortfolioSnapshot(timestamp=1700000000, cash=Decimal("10000"), positions={}, equity=Decimal("10000")),
            PortfolioSnapshot(timestamp=1700003600, cash=Decimal("9900"), positions={}, equity=Decimal("10150.25")),
        ]
        service.run.return_value = result
        journal = Mock()
        journal.entries.return_value = []

        detector = BacktestDriftDetector(service, journal)
        report = detector.detect("BTC_USD")

        assert [pnl for _, pnl in report.simulated_equity_curve] == [0.0, 150.25]

    def test_detect_populates_simulated_pnl_from_snapshots(self):
        service = Mock()
        service.build_request.return_value = Mock()
        result = Mock()
        result.fills = []
        result.initial_balance = Decimal("10000")
        result.portfolio_snapshots = [
            PortfolioSnapshot(timestamp=1700000000, cash=Decimal("10000"), positions={}, equity=Decimal("10000")),
            PortfolioSnapshot(timestamp=1700003600, cash=Decimal("10250"), positions={}, equity=Decimal("10250")),
        ]
        service.run.return_value = result
        journal = Mock()
        journal.entries.return_value = []

        detector = BacktestDriftDetector(service, journal)
        report = detector.detect("BTC_USD")

        assert report.simulated_pnl == Decimal("250")

    def test_detect_checks_out_explicit_commit_hash_from_vcs(self):
        service = Mock()
        service.build_request.return_value = Mock()
        result = Mock()
        result.fills = []
        result.portfolio_snapshots = []
        service.run.return_value = result
        journal = Mock()
        journal.entries.return_value = []
        vcs = Mock()
        vcs.checkout.return_value = {"assets": []}

        detector = BacktestDriftDetector(service, journal, vcs_service=vcs)
        detector.detect("BTC_USD", commit_hash="exp_commit_123")

        vcs.checkout.assert_called_once_with("exp_commit_123")

    def test_detect_defaults_to_main_ref_when_commit_hash_omitted(self):
        service = Mock()
        service.build_request.return_value = Mock()
        result = Mock()
        result.fills = []
        result.portfolio_snapshots = []
        service.run.return_value = result
        journal = Mock()
        journal.entries.return_value = []
        vcs = Mock()
        vcs.checkout.return_value = {"assets": []}

        detector = BacktestDriftDetector(service, journal, vcs_service=vcs)
        detector.detect("BTC_USD")

        vcs.checkout.assert_called_once_with("refs/heads/main")
