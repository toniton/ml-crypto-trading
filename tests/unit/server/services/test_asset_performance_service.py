# pylint: disable=duplicate-code
from datetime import datetime, timezone
from decimal import Decimal

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.core.interfaces.trading_engine_proxy import AssetRuntimeSnapshot
from src.server.services.asset_performance_service import AssetPerformanceService


def make_order(
        uuid: str,
        action: TradeAction,
        price: float,
        qty: str,
        dt: datetime,
        fees: float = 0.0,
        fill_price: float = None,
        slippage: float = 0.0,
) -> Order:
    return Order(
        uuid=uuid,
        provider_name="CRYPTO_DOT_COM",
        ticker_symbol="BTC_USD",
        price=Decimal(str(price)),
        fill_price=Decimal(str(fill_price or price)),
        quantity=qty,
        trade_action=action,
        status=OrderStatus.COMPLETED,
        created_time=dt.timestamp(),
        commit_hash="56339b9",
        executed_time=dt.timestamp(),
        fees=Decimal(str(fees)),
        slippage=Decimal(str(slippage)),
    )


def test_fifo_matching_basic():
    # BUY 0.10 @ 100 (fee 0.50)
    # BUY 0.10 @ 110 (fee 0.50)
    # SELL 0.15 @ 120 (fee 1.00)
    #
    # Match:
    # 0.10 from lot 1: gross (120 - 100)*0.10 = +2.00, buy_fee = 0.50, sell_fee = 1.00 * (0.10/0.15) = 0.67 -> net +0.83
    # 0.05 from lot 2: gross (120 - 110)*0.05 = +0.50, buy_fee = 0.25, sell_fee = 1.00 * (0.05/0.15) = 0.33 -> net -0.08
    dt1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    dt2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    dt3 = datetime(2026, 9, 3, 10, 0, 0, tzinfo=timezone.utc)

    orders = [
        make_order("o1", TradeAction.BUY, 100.0, "0.10", dt1, fees=0.50),
        make_order("o2", TradeAction.BUY, 110.0, "0.10", dt2, fees=0.50),
        make_order("o3", TradeAction.SELL, 120.0, "0.15", dt3, fees=1.00),
    ]

    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    end = datetime(2026, 9, 10, tzinfo=timezone.utc)

    res = AssetPerformanceService.compute_metrics("BTC_USD", start, end, orders)

    assert res.summary.trades == 3
    assert res.summary.buy_count == 2
    assert res.summary.sell_count == 1
    assert Decimal(res.summary.volume) == Decimal("39.00") # 10 + 11 + 18
    assert Decimal(res.summary.fees) == Decimal("2.00")

    # Realized P&L: Total gross (2.50) - Total fees matched (0.50 + 0.25 + 1.00 = 1.75) = +0.75
    assert Decimal(res.summary.realized_pnl) == Decimal("0.75")
    assert len(res.daily) == 3


def test_profit_factor_and_win_rate():
    # WIN: BUY 1 @ 100, SELL 1 @ 120 -> +20
    # LOSS: BUY 1 @ 100, SELL 1 @ 90 -> -10
    dt1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    dt2 = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    dt3 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    dt4 = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)

    orders = [
        make_order("o1", TradeAction.BUY, 100.0, "1.0", dt1),
        make_order("o2", TradeAction.SELL, 120.0, "1.0", dt2),
        make_order("o3", TradeAction.BUY, 100.0, "1.0", dt3),
        make_order("o4", TradeAction.SELL, 90.0, "1.0", dt4),
    ]

    res = AssetPerformanceService.compute_metrics(
        "BTC_USD", datetime(2026, 9, 1, tzinfo=timezone.utc), datetime(2026, 9, 10, tzinfo=timezone.utc), orders
    )

    assert res.summary.winning_trades == 1
    assert res.summary.losing_trades == 1
    assert res.summary.win_rate == 50.0
    assert Decimal(res.summary.realized_pnl) == Decimal("10.00")


def test_strategy_attribution_populated():
    dt1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    dt2 = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    o1 = make_order("o1", TradeAction.BUY, 100.0, "1.0", dt1)
    o1.winning_strategy = "TrendFollowing"
    o2 = make_order("o2", TradeAction.SELL, 120.0, "1.0", dt2)
    o2.winning_strategy = "TrendFollowing"

    res = AssetPerformanceService.compute_metrics(
        "BTC_USD", datetime(2026, 9, 1, tzinfo=timezone.utc), datetime(2026, 9, 10, tzinfo=timezone.utc), [o1, o2]
    )

    assert "TrendFollowing" in res.strategy_attribution
    assert res.strategy_attribution["TrendFollowing"].total_trades == 1
    assert res.strategy_attribution["TrendFollowing"].winning_trades == 1


def test_commit_attribution_populated():
    dt1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    dt2 = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    o1 = make_order("o1", TradeAction.BUY, 100.0, "1.0", dt1)
    o1.commit_hash = "c0ffee1"
    o2 = make_order("o2", TradeAction.SELL, 120.0, "1.0", dt2)
    o2.commit_hash = "c0ffee1"

    res = AssetPerformanceService.compute_metrics(
        "BTC_USD", datetime(2026, 9, 1, tzinfo=timezone.utc), datetime(2026, 9, 10, tzinfo=timezone.utc), [o1, o2]
    )

    assert "c0ffee1" in res.commit_attribution
    assert res.commit_attribution["c0ffee1"].win_rate_pct == 100.0


def test_extract_trades_and_compute_metrics_with_slippage():
    # BUY 10 @ 100, fee 1.00, slippage 0.50 ($0.05/unit entry slippage)
    # BUY 10 @ 100, fee 1.00, slippage 0.30 ($0.03/unit entry slippage)
    # SELL 20 @ 110, fee 2.00, slippage 0.20 ($0.01/unit exit slippage)
    #
    # Trade 1: matched against Lot 1 (qty 10)
    #   gross = (110 - 100) * 10 = +100
    #   fees = 1.00 (entry) + 1.00 (exit) = 2.00
    #   slippage = (0.05 * 10) + (0.01 * 10) = 0.50 + 0.10 = 0.60
    #   net_pnl = 100 - 2.00 - 0.60 = 97.40
    # Trade 2: matched against Lot 2 (qty 10)
    #   gross = (110 - 100) * 10 = +100
    #   fees = 1.00 (entry) + 1.00 (exit) = 2.00
    #   slippage = (0.03 * 10) + (0.01 * 10) = 0.30 + 0.10 = 0.40
    #   net_pnl = 100 - 2.00 - 0.40 = 97.60
    #
    # Total slippage conserved = 0.60 + 0.40 = 1.00 = 0.50 + 0.30 + 0.20
    # Total realized net P&L = 97.40 + 97.60 = 195.00
    dt1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    dt2 = datetime(2026, 9, 1, 11, 0, 0, tzinfo=timezone.utc)
    dt3 = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)

    orders = [
        make_order("o1", TradeAction.BUY, 100.0, "10", dt1, fees=1.00, slippage=0.50),
        make_order("o2", TradeAction.BUY, 100.0, "10", dt2, fees=1.00, slippage=0.30),
        make_order("o3", TradeAction.SELL, 110.0, "20", dt3, fees=2.00, slippage=0.20),
    ]

    trades = AssetPerformanceService.extract_trades("BTC_USD", orders)
    assert len(trades) == 2
    assert trades[0].slippage == Decimal("0.60")
    assert trades[1].slippage == Decimal("0.40")
    assert trades[0].net_pnl == Decimal("97.40")
    assert trades[1].net_pnl == Decimal("97.60")

    res = AssetPerformanceService.compute_metrics(
        "BTC_USD", datetime(2026, 9, 1, tzinfo=timezone.utc), datetime(2026, 9, 10, tzinfo=timezone.utc), orders
    )
    assert Decimal(res.summary.realized_pnl) == Decimal("195.00")
    assert res.risk_adjusted is not None
    assert res.behavior is not None
    assert res.execution is not None
    assert res.portfolio is not None
    assert res.execution.total_slippage_cost == Decimal("1.00")
    assert res.behavior.round_trips == 2
    assert res.behavior.winning_trades == 2


def test_extract_trades_with_audit_detects_unmatched_exits():
    dt = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    orders = [
        make_order("o_orphan", TradeAction.SELL, 110.0, "5", dt),
    ]

    extraction = AssetPerformanceService.extract_trades_with_audit("BTC_USD", orders)
    assert not extraction.trades
    assert extraction.unmatched_exit_quantity == Decimal("5")
    assert extraction.unmatched_exit_orders == 1


def test_equity_curve_tracks_cumulative_pnl_and_drawdown():
    dt1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    dt2 = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    dt3 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    dt4 = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)

    orders = [
        make_order("o1", TradeAction.BUY, 100.0, "10.0", dt1, fees=2.0),
        make_order("o2", TradeAction.SELL, 120.0, "10.0", dt2),
        make_order("o3", TradeAction.BUY, 100.0, "10.0", dt3),
        make_order("o4", TradeAction.SELL, 89.8, "10.0", dt4),
    ]

    res = AssetPerformanceService.compute_metrics(
        "BTC_USD",
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        datetime(2026, 9, 10, tzinfo=timezone.utc),
        orders,
    )

    assert [
        (pt.equity, pt.cumulative_pnl, pt.drawdown_pct)
        for pt in res.equity_curve
    ] == [
        ("1002.00", "+0.00", 0.0),
        ("1000.00", "-2.00", 0.2),
        ("1200.00", "+198.00", 0.0),
        ("1200.00", "+198.00", 0.0),
        ("1098.00", "+96.00", 8.5),
    ]


def test_equity_curve_uses_real_runtime_snapshot_balance_and_mark_to_market():
    dt1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    dt2 = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    dt3 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)

    orders = [
        make_order("o1", TradeAction.BUY, 100.0, "10.0", dt1),
        make_order("o2", TradeAction.SELL, 110.0, "10.0", dt2),
        make_order("o3", TradeAction.BUY, 110.0, "5.0", dt3),
    ]
    snapshot = AssetRuntimeSnapshot(
        ticker_symbol="BTC_USD",
        starting_balance=2500.0,
        available_balance=2050.0,
        position_quantity=5.0,
        latest_price=120.0,
    )

    res = AssetPerformanceService.compute_metrics(
        "BTC_USD",
        datetime(2026, 9, 1, tzinfo=timezone.utc),
        datetime(2026, 9, 10, tzinfo=timezone.utc),
        orders,
        runtime_snapshot=snapshot,
    )

    assert (
        res.starting_balance,
        res.current_equity,
        [(pt.equity, pt.cumulative_pnl) for pt in res.equity_curve],
    ) == (
        "2500.00",
        "2650.00",
        [
            ("2500.00", "+0.00"),
            ("2500.00", "+0.00"),
            ("2600.00", "+100.00"),
            ("2600.00", "+100.00"),
            ("2650.00", "+150.00"),
        ],
    )


def test_zero_mark_to_market_equity_is_preserved_not_overwritten():
    snapshot = AssetRuntimeSnapshot(
        ticker_symbol="BTC_USD",
        starting_balance=1000.0,
        available_balance=0.0,
        position_quantity=0.0,
        latest_price=50000.0,
    )
    init_bal, mtm = AssetPerformanceService._resolve_live_balances(
        snapshot,
        [],
        Decimal("0"),
    )
    assert mtm == Decimal("0.00")


def test_unknown_position_leaves_mark_to_market_equity_unavailable():
    snapshot = AssetRuntimeSnapshot(
        ticker_symbol="BTC_USD",
        starting_balance=1000.0,
        available_balance=500.0,
        position_quantity=None,
        latest_price=50000.0,
    )
    init_bal, mtm = AssetPerformanceService._resolve_live_balances(
        snapshot,
        [],
        Decimal("0"),
    )
    assert mtm == Decimal("1000.00")
    assert init_bal == Decimal("1000.00")

