from decimal import Decimal

from api.interfaces.position_lot import PositionLot
from src.trading.session.fifo_trade_matcher import FifoTradeMatcher


def _make_lot(
        order_uuid: str,
        quantity: str,
        price: str,
        fee: str = "0.1",
        timestamp: float = 1700000000.0,
        strategy: str = "RsiStrategy",
) -> PositionLot:
    return PositionLot.create(
        order_uuid=order_uuid,
        ticker_symbol="BTC_USD",
        price=Decimal(price),
        quantity=Decimal(quantity),
        fee=Decimal(fee),
        timestamp=timestamp,
        winning_strategy=strategy,
        strategy_votes={strategy: "BUY"},
    )


class TestFifoTradeMatcherSingleLot:
    def test_single_lot_full_close(self):
        lots = [_make_lot(order_uuid="entry-1", quantity="10", price="100")]

        trades, unallocated = FifoTradeMatcher.match_lots(
            lots=lots,
            ticker_symbol="BTC_USD",
            exit_order_uuid="exit-1",
            exit_price=Decimal("110"),
            exit_quantity=Decimal("10"),
            exit_fee=Decimal("1.0"),
            exit_timestamp=1700001000.0,
        )

        assert len(trades) == 1
        assert unallocated == Decimal("0")
        assert len(lots) == 0

    def test_single_lot_partial_close(self):
        lots = [_make_lot(order_uuid="entry-1", quantity="10", price="100")]

        trades, unallocated = FifoTradeMatcher.match_lots(
            lots=lots,
            ticker_symbol="BTC_USD",
            exit_order_uuid="exit-1",
            exit_price=Decimal("110"),
            exit_quantity=Decimal("4"),
            exit_fee=Decimal("0.4"),
            exit_timestamp=1700001000.0,
        )

        assert len(trades) == 1
        assert trades[0].quantity == Decimal("4")
        assert unallocated == Decimal("0")
        assert len(lots) == 1
        assert lots[0].remaining_quantity == Decimal("6")


class TestFifoTradeMatcherMultiLotSlippage:
    def test_multi_lot_slippage_allocated_proportionally(self):
        lot_a = _make_lot(order_uuid="entry-a", quantity="10", price="100", fee="1.0")
        lot_b = _make_lot(order_uuid="entry-b", quantity="10", price="100", fee="1.0")
        lots = [lot_a, lot_b]

        trades, unallocated = FifoTradeMatcher.match_lots(
            lots=lots,
            ticker_symbol="BTC_USD",
            exit_order_uuid="exit-1",
            exit_price=Decimal("110"),
            exit_quantity=Decimal("20"),
            exit_fee=Decimal("2.0"),
            exit_timestamp=1700001000.0,
            exit_slippage=Decimal("0.20"),
        )

        assert len(trades) == 2
        assert trades[0].slippage == Decimal("0.10")
        assert trades[1].slippage == Decimal("0.10")
        assert unallocated == Decimal("0")
