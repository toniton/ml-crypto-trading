from decimal import Decimal

from api.interfaces.trade import Trade
from src.trading.analytics.trade_attribution_service import TradeAttributionService


def _sample_trades() -> list[Trade]:
    return [
        Trade.create(
            ticker_symbol="BTC_USD",
            entry_order_uuid="e-1",
            exit_order_uuid="x-1",
            entry_price=Decimal("100"),
            exit_price=Decimal("110"),
            quantity=Decimal("2"),
            entry_fee=Decimal("1"),
            exit_fee=Decimal("1"),
            entry_timestamp=100.0,
            exit_timestamp=160.0,
            commit_hash="commit_a",
            winning_strategy="HammerStrategy",
        ),
        Trade.create(
            ticker_symbol="BTC_USD",
            entry_order_uuid="e-2",
            exit_order_uuid="x-2",
            entry_price=Decimal("100"),
            exit_price=Decimal("95"),
            quantity=Decimal("2"),
            entry_fee=Decimal("1"),
            exit_fee=Decimal("1"),
            entry_timestamp=200.0,
            exit_timestamp=250.0,
            commit_hash="commit_a",
            winning_strategy="GridStrategy",
        ),
        Trade.create(
            ticker_symbol="ETH_USD",
            entry_order_uuid="e-3",
            exit_order_uuid="x-3",
            entry_price=Decimal("2000"),
            exit_price=Decimal("2100"),
            quantity=Decimal("1"),
            entry_fee=Decimal("5"),
            exit_fee=Decimal("5"),
            entry_timestamp=300.0,
            exit_timestamp=330.0,
            commit_hash="commit_b",
            winning_strategy="HammerStrategy",
        ),
    ]


class TestTradeAttributionService:
    def test_calculate_metrics_total_trades(self):
        trades = _sample_trades()
        metrics = TradeAttributionService.calculate_metrics(trades)
        assert metrics.total_trades == 3

    def test_calculate_metrics_win_rate(self):
        trades = _sample_trades()
        metrics = TradeAttributionService.calculate_metrics(trades)
        assert metrics.win_rate_pct == 66.67

    def test_calculate_metrics_net_pnl(self):
        trades = _sample_trades()
        metrics = TradeAttributionService.calculate_metrics(trades)
        # Trade 1: gross 20 - 2 fees = 18
        # Trade 2: gross -10 - 2 fees = -12
        # Trade 3: gross 100 - 10 fees = 90
        # Total net = 18 - 12 + 90 = 96
        assert metrics.net_pnl == Decimal("96")

    def test_attribute_by_commit(self):
        trades = _sample_trades()
        by_commit = TradeAttributionService.attribute_by_commit(trades)
        assert "commit_a" in by_commit and "commit_b" in by_commit

    def test_attribute_by_commit_metrics(self):
        trades = _sample_trades()
        by_commit = TradeAttributionService.attribute_by_commit(trades)
        assert by_commit["commit_a"].net_pnl == Decimal("6")

    def test_attribute_by_strategy(self):
        trades = _sample_trades()
        by_strategy = TradeAttributionService.attribute_by_strategy(trades)
        assert by_strategy["HammerStrategy"].winning_trades == 2

    def test_attribute_by_symbol(self):
        trades = _sample_trades()
        by_symbol = TradeAttributionService.attribute_by_symbol(trades)
        assert by_symbol["ETH_USD"].net_pnl == Decimal("90")

    def test_empty_trades_returns_zero_metrics(self):
        metrics = TradeAttributionService.calculate_metrics([])
        assert metrics.total_trades == 0
