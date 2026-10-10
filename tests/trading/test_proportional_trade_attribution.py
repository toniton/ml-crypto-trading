from __future__ import annotations

from decimal import Decimal

from api.interfaces.trade import Trade
from src.trading.analytics.trade_attribution_service import TradeAttributionService


def _make_trade(
        entry_price: Decimal = Decimal(100),
        exit_price: Decimal = Decimal(110),
        quantity: Decimal = Decimal(10),
        fees: Decimal = Decimal(10),
        slippage: Decimal = Decimal(2),
        winning_strategy: str = "Momentum",
        entry_strategy_attributions: dict[str, float] | None = None,
        strategy_votes: dict[str, str] | None = None,
) -> Trade:
    return Trade.create(
        ticker_symbol="BTC_USD",
        entry_order_uuid="entry-1",
        exit_order_uuid="exit-1",
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        entry_fee=fees / Decimal(2),
        exit_fee=fees / Decimal(2),
        entry_timestamp=1000.0,
        exit_timestamp=1100.0,
        slippage=slippage,
        winning_strategy=winning_strategy,
        entry_strategy_attributions=entry_strategy_attributions,
        strategy_votes=strategy_votes,
    )


def test_proportional_attribution_equal_weights():
    # 2 strategies co-voted with equal weights (50% each)
    # gross_pnl = (110 - 100) * 10 = 100, fees = 15, slippage = 5 -> net_pnl = 80
    t1 = _make_trade(
        entry_price=Decimal(100),
        exit_price=Decimal(110),
        quantity=Decimal(10),
        fees=Decimal("15.0"),
        slippage=Decimal("5.0"),
        entry_strategy_attributions={"StrategyA": 0.5, "StrategyB": 0.5},
    )

    attr = TradeAttributionService.attribute_by_strategy_proportional([t1])

    assert "StrategyA" in attr
    assert "StrategyB" in attr
    assert attr["StrategyA"].total_trades == 1
    assert attr["StrategyA"].winning_trades == 1
    assert attr["StrategyA"].net_pnl == Decimal("40.00")
    assert attr["StrategyA"].gross_pnl == Decimal("50.00")
    assert attr["StrategyA"].total_fees == Decimal("7.50")
    assert attr["StrategyA"].total_slippage == Decimal("2.50")

    assert attr["StrategyB"].net_pnl == Decimal("40.00")
    assert attr["StrategyB"].gross_pnl == Decimal("50.00")


def test_proportional_attribution_asymmetric_weights():
    # StrategyA 80%, StrategyB 20%
    # gross_pnl = 100, fees = 15, slippage = 5 -> net_pnl = 80
    t1 = _make_trade(
        entry_price=Decimal(100),
        exit_price=Decimal(110),
        quantity=Decimal(10),
        fees=Decimal("15.0"),
        slippage=Decimal("5.0"),
        entry_strategy_attributions={"StrategyA": 0.8, "StrategyB": 0.2},
    )

    attr = TradeAttributionService.attribute_by_strategy_proportional([t1])

    assert attr["StrategyA"].net_pnl == Decimal("64.00")
    assert attr["StrategyB"].net_pnl == Decimal("16.00")


def test_proportional_attribution_fallback_for_legacy_trades():
    # Legacy trade without entry_strategy_attributions map (gross=100, fees=10, slippage=2 -> net_pnl=88)
    t1 = _make_trade(
        winning_strategy="LegacyMomentum",
        entry_strategy_attributions=None,
    )

    attr = TradeAttributionService.attribute_by_strategy_proportional([t1])

    assert "LegacyMomentum" in attr
    assert attr["LegacyMomentum"].net_pnl == Decimal("88.00")
    assert attr["LegacyMomentum"].total_trades == 1


def test_compute_co_voting_matrix():
    t1 = _make_trade(
        strategy_votes={"StratA": "TRUE", "StratB": "TRUE", "StratC": "FALSE"},
    )
    t2 = _make_trade(
        strategy_votes={"StratA": "TRUE", "StratB": "FALSE", "StratC": "TRUE"},
    )

    matrix = TradeAttributionService.compute_co_voting_matrix([t1, t2])

    # StratA and StratB evaluated both t1 and t2: agreed in t1 (both TRUE), disagreed in t2 (TRUE vs FALSE).
    # Agreement rate is 1 / 2 = 50% in both directions.
    assert matrix["StratA"]["StratB"] == 0.5
    assert matrix["StratA"]["StratC"] == 0.5
    assert matrix["StratA"]["StratA"] == 1.0
    assert matrix["StratB"]["StratA"] == 0.5


def test_compute_co_voting_matrix_standardized_string_votes():
    # Verify string BUY, SELL, HOLD votes are recognized and compared across aligned decisions
    t1 = _make_trade(
        strategy_votes={"Trend": "BUY", "MeanRev": "BUY", "Filter": "HOLD"},
    )
    t2 = _make_trade(
        strategy_votes={"Trend": "BUY", "MeanRev": "SELL", "Filter": "HOLD"},
    )
    t3 = _make_trade(
        strategy_votes={"Trend": "SELL", "MeanRev": "SELL", "Filter": "HOLD"},
    )

    matrix = TradeAttributionService.compute_co_voting_matrix([t1, t2, t3])

    # Trend and MeanRev agreed in t1 (BUY/BUY) and t3 (SELL/SELL), disagreed in t2 (BUY/SELL) -> 2/3 = 0.6667
    assert matrix["Trend"]["MeanRev"] == 0.6667
    assert matrix["MeanRev"]["Trend"] == 0.6667
    # Filter voted HOLD in all 3 -> agreed with itself 100%
    assert matrix["Filter"]["Filter"] == 1.0
    # Trend and Filter never agreed (BUY!=HOLD, SELL!=HOLD) -> 0.0
    assert matrix["Trend"]["Filter"] == 0.0


def test_proportional_attribution_pnl_conservation():
    # Conservation law invariant: sum(net_pnl(s)) == total_realized_net_pnl
    t1 = _make_trade(
        entry_price=Decimal("100"),
        exit_price=Decimal("110"),
        quantity=Decimal("10"),
        fees=Decimal("14.50"),
        slippage=Decimal("3.20"),
        entry_strategy_attributions={"Strat1": 0.6, "Strat2": 0.4},
    )
    t2 = _make_trade(
        entry_price=Decimal("100"),
        exit_price=Decimal("95"),
        quantity=Decimal("5"),
        fees=Decimal("8.00"),
        slippage=Decimal("1.50"),
        entry_strategy_attributions={"Strat2": 0.7, "Strat3": 0.3},
    )
    t3 = _make_trade(
        entry_price=Decimal("100"),
        exit_price=Decimal("105"),
        quantity=Decimal("2"),
        fees=Decimal("2.00"),
        slippage=Decimal("0.50"),
        winning_strategy="LegacyStrat",
        entry_strategy_attributions=None,  # Legacy trade
    )

    all_trades = [t1, t2, t3]
    total_expected_net = sum(t.net_pnl for t in all_trades)
    total_expected_fees = sum(t.fees for t in all_trades)
    total_expected_slippage = sum(t.slippage for t in all_trades)

    attr = TradeAttributionService.attribute_by_strategy_proportional(all_trades)

    sum_attr_net = sum(m.net_pnl for m in attr.values())
    sum_attr_fees = sum(m.total_fees for m in attr.values())
    sum_attr_slippage = sum(m.total_slippage for m in attr.values())

    assert sum_attr_net == total_expected_net
    assert sum_attr_fees == total_expected_fees
    assert sum_attr_slippage == total_expected_slippage


def test_attribute_by_participation():
    # Trade 1 co-sponsored by StratA and StratB (net_pnl = 80)
    t1 = _make_trade(
        entry_strategy_attributions={"StratA": 0.5, "StratB": 0.5},
        fees=Decimal("15"),
        slippage=Decimal("5"),
    )
    # Trade 2 sponsored only by StratA (net_pnl = 80)
    t2 = _make_trade(
        entry_strategy_attributions={"StratA": 1.0},
        fees=Decimal("15"),
        slippage=Decimal("5"),
    )

    part_attr = TradeAttributionService.attribute_by_participation([t1, t2])
    # StratA participated in 2 trades, total unscaled net_pnl = 160
    assert part_attr["StratA"].total_trades == 2
    assert part_attr["StratA"].net_pnl == Decimal("160")
    # StratB participated in 1 trade, total unscaled net_pnl = 80
    assert part_attr["StratB"].total_trades == 1
    assert part_attr["StratB"].net_pnl == Decimal("80")


def test_attribute_by_entry_vs_exit_provenance():
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
        exit_timestamp=1050.0,
        winning_strategy="EntryMomentum",
        exit_winning_strategy="ExitRsi",
        entry_strategy_attributions={"EntryMomentum": 1.0},
        exit_strategy_attributions={"ExitRsi": 1.0},
    )

    evx = TradeAttributionService.attribute_by_entry_vs_exit([trade])
    assert "EntryMomentum" in evx["entry"]
    assert evx["entry"]["EntryMomentum"].total_trades == 1
    assert "ExitRsi" in evx["exit"]
    assert evx["exit"]["ExitRsi"].total_trades == 1
