# pylint: disable=duplicate-code
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

    def test_attribute_by_strategy_multi_entry_and_exit(self):
        trade = Trade.create(
            ticker_symbol="BTC_USD",
            entry_order_uuid="e-1",
            exit_order_uuid="x-1",
            entry_price=Decimal("100"),
            exit_price=Decimal("110"),
            quantity=Decimal("1"),
            entry_fee=Decimal("1"),
            exit_fee=Decimal("1"),
            entry_timestamp=1000.0,
            exit_timestamp=1100.0,
            entry_strategy_attributions={"RsiBuy": 0.6, "TrendBuy": 0.4},
            exit_strategy_attributions={"StopLossSell": 1.0},
        )
        by_strat = TradeAttributionService.attribute_by_strategy([trade])
        assert set(by_strat.keys()) == {"RsiBuy", "TrendBuy", "StopLossSell"}

    def test_compute_co_voting_details_cross_strategy(self):
        trade = Trade.create(
            ticker_symbol="BTC_USD",
            entry_order_uuid="e-1",
            exit_order_uuid="x-1",
            entry_price=Decimal("100"),
            exit_price=Decimal("110"),
            quantity=Decimal("1"),
            entry_fee=Decimal("1"),
            exit_fee=Decimal("1"),
            entry_timestamp=1000.0,
            exit_timestamp=1100.0,
            entry_strategy_attributions={"RsiBuy": 1.0},
            exit_strategy_attributions={"StopLossSell": 1.0},
        )
        matrix, counts = TradeAttributionService.compute_co_voting_details([trade])
        assert matrix["RsiBuy"]["StopLossSell"] == 1.0
        assert counts["RsiBuy"]["StopLossSell"] == 1

    def test_empty_trades_returns_zero_metrics(self):
        metrics = TradeAttributionService.calculate_metrics([])
        assert metrics.total_trades == 0

    def test_attribute_by_regime_groups_correctly(self):
        trades = [
            Trade.create(
                ticker_symbol="BTC_USD",
                entry_order_uuid="e-1",
                exit_order_uuid="x-1",
                entry_price=Decimal("100"),
                exit_price=Decimal("110"),
                quantity=Decimal("1"),
                entry_fee=Decimal("1"),
                exit_fee=Decimal("1"),
                entry_timestamp=100.0,
                exit_timestamp=160.0,
                entry_regime="TRENDING_UP",
            ),
            Trade.create(
                ticker_symbol="BTC_USD",
                entry_order_uuid="e-2",
                exit_order_uuid="x-2",
                entry_price=Decimal("100"),
                exit_price=Decimal("90"),
                quantity=Decimal("1"),
                entry_fee=Decimal("1"),
                exit_fee=Decimal("1"),
                entry_timestamp=200.0,
                exit_timestamp=260.0,
                entry_regime="TRENDING_DOWN",
            ),
        ]
        result = TradeAttributionService.attribute_by_regime(trades)
        assert set(result.keys()) == {"TRENDING_UP", "TRENDING_DOWN"}

    def test_attribute_strategy_by_regime_segments_performance(self):
        trade = Trade.create(
            ticker_symbol="BTC_USD",
            entry_order_uuid="e-1",
            exit_order_uuid="x-1",
            entry_price=Decimal("100"),
            exit_price=Decimal("110"),
            quantity=Decimal("1"),
            entry_fee=Decimal("1"),
            exit_fee=Decimal("1"),
            entry_timestamp=100.0,
            exit_timestamp=160.0,
            entry_strategy_attributions={"TrendBuy": 1.0},
            entry_regime="HIGH_VOLATILITY",
        )
        matrix = TradeAttributionService.attribute_strategy_by_regime([trade])
        assert matrix["TrendBuy"]["HIGH_VOLATILITY"].winning_trades == 1

    def test_compute_co_voting_by_regime_partitions_votes(self):
        trade = Trade.create(
            ticker_symbol="BTC_USD",
            entry_order_uuid="e-1",
            exit_order_uuid="x-1",
            entry_price=Decimal("100"),
            exit_price=Decimal("110"),
            quantity=Decimal("1"),
            entry_fee=Decimal("1"),
            exit_fee=Decimal("1"),
            entry_timestamp=100.0,
            exit_timestamp=160.0,
            strategy_votes={"TrendBuy": "BUY", "RsiBuy": "BUY"},
            entry_regime="RANGING",
        )
        by_regime = TradeAttributionService.compute_co_voting_by_regime([trade])
        assert "ALL" in by_regime and "RANGING" in by_regime
