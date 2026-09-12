from datetime import datetime, timezone
from decimal import Decimal

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.server.services.asset_performance_service import AssetPerformanceService


def make_order(
        uuid: str,
        action: TradeAction,
        price: float,
        qty: str,
        dt: datetime,
        fees: float = 0.0,
        fill_price: float = None,
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
        executed_time=dt.timestamp(),
        fees=Decimal(str(fees)),
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
    assert res.summary.profit_factor == 2.0 # 20 / 10
    assert Decimal(res.summary.realized_pnl) == Decimal("10.00")
