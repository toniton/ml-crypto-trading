from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from api.interfaces.trade import Trade
from src.core.weekday import Weekday
from src.trading.analytics.strategy_optimizer import (
    StrategyOptimizer,
)


def _make_trade(
        entry_price: Decimal = Decimal("100"),
        exit_price: Decimal = Decimal("110"),
        quantity: Decimal = Decimal("10"),
        fees: Decimal = Decimal("2"),
        slippage: Decimal = Decimal("0"),
        entry_timestamp: float = 1781085600.0,  # 2026-06-10 10:00:00 UTC (Wednesday 12:00 Stockholm)
        winning_strategy: str = "Momentum",
        entry_strategy_attributions: dict[str, float] | None = None,
) -> Trade:
    return Trade.create(
        ticker_symbol="BTC_USD",
        entry_order_uuid="e-1",
        exit_order_uuid="x-1",
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        entry_fee=fees / Decimal("2"),
        exit_fee=fees / Decimal("2"),
        entry_timestamp=entry_timestamp,
        exit_timestamp=entry_timestamp + 600.0,
        slippage=slippage,
        winning_strategy=winning_strategy,
        entry_strategy_attributions=entry_strategy_attributions or {winning_strategy: 1.0},
    )


def test_calibrate_strategy_weights_increases_high_performer():
    # StratA has 5 winning trades (high win rate & PF)
    # StratB has 5 losing trades
    trades = []
    for i in range(5):
        t_win = _make_trade(
            entry_price=Decimal("100"),
            exit_price=Decimal("120"),
            winning_strategy="StratA",
            entry_strategy_attributions={"StratA": 0.5, "StratB": 0.5},
            entry_timestamp=1781085600.0 + i * 3600,
        )
        trades.append(t_win)

    for i in range(5):
        t_loss = _make_trade(
            entry_price=Decimal("100"),
            exit_price=Decimal("80"),
            winning_strategy="StratB",
            entry_strategy_attributions={"StratB": 1.0},
            entry_timestamp=1781085600.0 + (i + 5) * 3600,
        )
        trades.append(t_loss)

    current_weights = {"StratA": 1.0, "StratB": 1.0}
    recs = StrategyOptimizer.calibrate_strategy_weights(trades, current_weights)

    rec_map = {r.strategy_name: r for r in recs}
    assert "StratA" in rec_map
    assert "StratB" in rec_map
    assert rec_map["StratA"].recommended_weight > 1.0
    assert rec_map["StratB"].recommended_weight < 1.0
    assert rec_map["StratA"].win_rate_pct == 100.0


def test_profile_hourly_profitability():
    # Wednesday 10:00 UTC is Wednesday 12:00 in Stockholm (UTC+2 in summer)
    t1 = _make_trade(
        entry_timestamp=datetime(2026, 6, 10, 10, 0, 0, tzinfo=timezone.utc).timestamp(),
        entry_price=Decimal("100"),
        exit_price=Decimal("110"),
    )
    t2 = _make_trade(
        entry_timestamp=datetime(2026, 6, 10, 10, 30, 0, tzinfo=timezone.utc).timestamp(),
        entry_price=Decimal("100"),
        exit_price=Decimal("115"),
    )

    profiles = StrategyOptimizer.profile_hourly_profitability([t1, t2], timezone_str="Europe/Stockholm")
    assert len(profiles) == 1
    assert profiles[0].weekday == Weekday.WEDNESDAY
    assert profiles[0].hour == 12
    assert profiles[0].total_trades == 2
    assert profiles[0].winning_trades == 2
    assert profiles[0].win_rate_pct == 100.0


def test_optimize_trading_windows_finds_contiguous_blocks():
    # Trades across Wed 10:00, 11:00, 12:00 UTC (12:00, 13:00, 14:00 Stockholm)
    trades = [
        _make_trade(
            entry_timestamp=datetime(2026, 6, 10, h, 0, 0, tzinfo=timezone.utc).timestamp(),
            entry_price=Decimal("100"),
            exit_price=Decimal("110"),
        )
        for h in [10, 11, 12]
    ]

    windows = StrategyOptimizer.optimize_trading_windows(
        trades,
        timezone_str="Europe/Stockholm",
        min_trades=1,
    )

    assert len(windows) == 1
    w = windows[0]
    assert w.days == [Weekday.WEDNESDAY]
    assert w.start_time.hour == 12
    assert w.end_time.hour == 15  # 12:00 to 15:00 contiguous (12, 13, 14 inclusive)


def test_detect_strategy_redundancies():
    # StratA and StratB always vote together (100% agreement)
    trades = [
        _make_trade(
            winning_strategy="StratA",
            entry_strategy_attributions={"StratA": 0.5, "StratB": 0.5},
            entry_timestamp=1781085600.0 + i * 1000,
        )
        for i in range(4)
    ]

    redundancies = StrategyOptimizer.detect_strategy_redundancies(trades, agreement_threshold=0.85)
    assert len(redundancies) == 1
    assert redundancies[0].strategy_a == "StratA"
    assert redundancies[0].strategy_b == "StratB"
    assert redundancies[0].agreement_rate_pct == 100.0


def test_generate_optimization_proposal():
    trades = [
        _make_trade(
            entry_price=Decimal("100"),
            exit_price=Decimal("120"),
            winning_strategy="TrendA",
            entry_strategy_attributions={"TrendA": 1.0},
            entry_timestamp=datetime(2026, 6, 10, 10, 0, 0, tzinfo=timezone.utc).timestamp() + i * 60,
        )
        for i in range(4)
    ]

    current_config = {
        "strategies": [
            {
                "name": "TrendA",
                "weight": 1.0,
                "schedule": {"timezone": "UTC", "windows": []},
            }
        ]
    }

    proposal = StrategyOptimizer.generate_optimization_proposal(
        ticker_symbol="BTC_USD",
        current_asset_config=current_config,
        trades=trades,
        timezone_str="UTC",
    )

    assert len(proposal.changes) > 0
    paths = [c.path for c in proposal.changes]
    assert any("assets.BTC_USD.strategies.TrendA" in p for p in paths)
    assert "Autonomous calibration" in proposal.summary


def test_profile_hourly_profitability_defaults_to_utc():
    t = _make_trade(
        entry_timestamp=datetime(2026, 6, 10, 14, 0, 0, tzinfo=timezone.utc).timestamp(),
        entry_price=Decimal("100"),
        exit_price=Decimal("110"),
    )
    profiles = StrategyOptimizer.profile_hourly_profitability([t])
    assert len(profiles) == 1
    assert profiles[0].hour == 14  # Unaltered UTC hour


def test_optimize_trading_windows_enforces_strict_sample_size():
    # 1 profitable trade should NOT qualify when min_trades=2
    t = _make_trade(
        entry_timestamp=datetime(2026, 6, 10, 14, 0, 0, tzinfo=timezone.utc).timestamp(),
        entry_price=Decimal("100"),
        exit_price=Decimal("110"),
    )
    windows = StrategyOptimizer.optimize_trading_windows([t], min_trades=2)
    assert len(windows) == 0


def test_optimize_strategy_trading_windows():
    # StratA has 2 winning trades at 10:00 UTC; StratB has 2 losing trades at 14:00 UTC
    t1 = _make_trade(
        winning_strategy="StratA",
        entry_strategy_attributions={"StratA": 1.0},
        entry_timestamp=datetime(2026, 6, 10, 10, 0, 0, tzinfo=timezone.utc).timestamp(),
        entry_price=Decimal("100"),
        exit_price=Decimal("110"),
    )
    t2 = _make_trade(
        winning_strategy="StratA",
        entry_strategy_attributions={"StratA": 1.0},
        entry_timestamp=datetime(2026, 6, 10, 10, 30, 0, tzinfo=timezone.utc).timestamp(),
        entry_price=Decimal("100"),
        exit_price=Decimal("115"),
    )
    t3 = _make_trade(
        winning_strategy="StratB",
        entry_strategy_attributions={"StratB": 1.0},
        entry_timestamp=datetime(2026, 6, 10, 14, 0, 0, tzinfo=timezone.utc).timestamp(),
        entry_price=Decimal("100"),
        exit_price=Decimal("90"),
    )

    windows_a = StrategyOptimizer.optimize_strategy_trading_windows(
        [t1, t2, t3],
        strategy_name="StratA",
        min_trades=2,
    )
    windows_b = StrategyOptimizer.optimize_strategy_trading_windows(
        [t1, t2, t3],
        strategy_name="StratB",
        min_trades=2,
    )

    assert len(windows_a) == 1
    assert windows_a[0].start_time.hour == 10
    assert len(windows_b) == 0


def test_generate_optimization_proposal_suppresses_unchanged_schedule_and_binds_commit():
    trades = [
        _make_trade(
            entry_price=Decimal("100"),
            exit_price=Decimal("120"),
            winning_strategy="TrendA",
            entry_strategy_attributions={"TrendA": 1.0},
            entry_timestamp=datetime(2026, 6, 10, 10, 0, 0, tzinfo=timezone.utc).timestamp() + i * 3600,
        )
        for i in range(4)
    ]

    discovered_windows = StrategyOptimizer.optimize_trading_windows(trades)
    current_windows_payload = [
        {
            "days": [d.value for d in w.days],
            "start_time": w.start_time.strftime("%H:%M:%S"),
            "end_time": w.end_time.strftime("%H:%M:%S"),
        }
        for w in discovered_windows
    ]

    # Pre-configure TrendA with the exact discovered windows
    current_config = {
        "strategies": [
            {
                "name": "TrendA",
                "weight": 1.0,
                "schedule": {"timezone": "UTC", "windows": current_windows_payload},
            }
        ]
    }

    proposal = StrategyOptimizer.generate_optimization_proposal(
        ticker_symbol="BTC_USD",
        current_asset_config=current_config,
        trades=trades,
        base_commit_hash="commit-abc-123",
    )

    assert proposal.base_commit_hash == "commit-abc-123"
    schedule_changes = [c for c in proposal.changes if "schedule.windows" in c.path]
    # Since existing schedule equals discovered windows, no schedule change diff should be emitted
    assert len(schedule_changes) == 0


def test_strategy_schedule_without_evidence_is_not_given_asset_windows_by_default():
    base_ts = datetime(2026, 6, 10, 10, 0, 0, tzinfo=timezone.utc).timestamp()
    trades = [
        _make_trade(
            entry_price=Decimal("100"),
            exit_price=Decimal("120"),
            winning_strategy="TrendA",
            entry_strategy_attributions={"TrendA": 1.0},
            entry_timestamp=base_ts + i * 60,
        )
        for i in range(4)
    ]

    current_config = {
        "strategies": [
            {
                "name": "TrendA",
                "weight": 1.0,
                "schedule": {"timezone": "UTC", "windows": []},
            },
            {
                "name": "TrendB_NoEvidence",
                "weight": 1.0,
                "schedule": {"timezone": "UTC", "windows": []},
            },
        ]
    }

    # Default: allow_asset_fallback is False
    proposal = StrategyOptimizer.generate_optimization_proposal(
        ticker_symbol="BTC_USD",
        current_asset_config=current_config,
        trades=trades,
        allow_asset_fallback=False,
    )

    sched_changes = [c for c in proposal.changes if "schedule.windows" in c.path]
    # TrendA has evidence and gets a schedule change
    assert any("TrendA" in c.path for c in sched_changes)
    # TrendB has NO evidence and should NOT receive a fabricated schedule
    assert not any("TrendB_NoEvidence" in c.path for c in sched_changes)

    # When explicit fallback is enabled, TrendB receives the fallback
    fallback_prop = StrategyOptimizer.generate_optimization_proposal(
        ticker_symbol="BTC_USD",
        current_asset_config=current_config,
        trades=trades,
        allow_asset_fallback=True,
    )
    fallback_changes = [c for c in fallback_prop.changes if "schedule.windows" in c.path]
    trend_b_change = next(c for c in fallback_changes if "TrendB_NoEvidence" in c.path)
    assert "Applied aggregate asset-level trading windows fallback" in trend_b_change.reason
