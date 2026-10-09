from decimal import Decimal

from api.interfaces.position_lot import PositionLot
from src.trading.session.fifo_trade_matcher import FifoTradeMatcher


def _make_lot(
        order_uuid: str,
        quantity: str,
        price: str,
        fee: str = "0.1",
        slippage: str = "0.0",
        timestamp: float = 1700000000.0,
        strategy: str = "RsiStrategy",
) -> PositionLot:
    return PositionLot.create(
        order_uuid=order_uuid,
        ticker_symbol="BTC_USD",
        price=Decimal(price),
        quantity=Decimal(quantity),
        fee=Decimal(fee),
        slippage=Decimal(slippage),
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

    def test_entry_and_exit_slippage_combined_and_conserved(self):
        # Lot A: 10 units with $0.50 entry slippage ($0.05/unit)
        # Lot B: 10 units with $0.30 entry slippage ($0.03/unit)
        # SELL: 20 units with $0.20 exit slippage ($0.01/unit)
        lot_a = _make_lot(order_uuid="entry-a", quantity="10", price="100", fee="1.0", slippage="0.50")
        lot_b = _make_lot(order_uuid="entry-b", quantity="10", price="100", fee="1.0", slippage="0.30")
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
        assert trades[0].slippage == Decimal("0.60")  # (0.05 * 10) + (0.01 * 10)
        assert trades[1].slippage == Decimal("0.40")  # (0.03 * 10) + (0.01 * 10)
        assert sum(t.slippage for t in trades) == Decimal("1.00")
        assert unallocated == Decimal("0")

    def test_partial_lot_entry_and_exit_slippage_conserved(self):
        # Lot A: 10 units with $0.50 entry slippage ($0.05/unit)
        # SELL: 4 units with $0.08 exit slippage ($0.02/unit)
        lot_a = _make_lot(order_uuid="entry-a", quantity="10", price="100", fee="1.0", slippage="0.50")
        lots = [lot_a]

        trades, unallocated = FifoTradeMatcher.match_lots(
            lots=lots,
            ticker_symbol="BTC_USD",
            exit_order_uuid="exit-1",
            exit_price=Decimal("110"),
            exit_quantity=Decimal("4"),
            exit_fee=Decimal("0.4"),
            exit_timestamp=1700001000.0,
            exit_slippage=Decimal("0.08"),
        )

        assert len(trades) == 1
        assert trades[0].slippage == Decimal("0.28")  # (0.05 * 4) + (0.02 * 4)
        assert len(lots) == 1
        assert lots[0].remaining_quantity == Decimal("6")
        assert lots[0].slippage_per_unit == Decimal("0.05")
        assert unallocated == Decimal("0")


class TestFifoTradeMatcherStrategyAttribution:
    def test_multi_lot_entry_and_exit_strategy_provenance(self):
        # Lot A opened by Momentum, Lot B opened by TrendFollowing
        lot_a = PositionLot.create(
            order_uuid="entry-a",
            ticker_symbol="BTC_USD",
            price=Decimal("100"),
            quantity=Decimal("10"),
            fee=Decimal("1.0"),
            slippage=Decimal("0.0"),
            timestamp=1000.0,
            winning_strategy="Momentum",
            strategy_attributions={"Momentum": 1.0},
        )
        lot_b = PositionLot.create(
            order_uuid="entry-b",
            ticker_symbol="BTC_USD",
            price=Decimal("102"),
            quantity=Decimal("10"),
            fee=Decimal("1.0"),
            slippage=Decimal("0.0"),
            timestamp=1050.0,
            winning_strategy="TrendFollowing",
            strategy_attributions={"TrendFollowing": 1.0},
        )
        lots = [lot_a, lot_b]

        # Exit order closed by RsiSell
        trades, unallocated = FifoTradeMatcher.match_lots(
            lots=lots,
            ticker_symbol="BTC_USD",
            exit_order_uuid="exit-1",
            exit_price=Decimal("110"),
            exit_quantity=Decimal("20"),
            exit_fee=Decimal("2.0"),
            exit_timestamp=1100.0,
            winning_strategy="RsiSell",
            strategy_attributions={"RsiSell": 1.0},
        )

        assert len(trades) == 2
        assert unallocated == Decimal("0")
        # Trade 1 preserves Lot A's entry provenance while recording RsiSell exit
        assert trades[0].entry_strategy_attributions == {"Momentum": 1.0}
        assert trades[0].exit_strategy_attributions == {"RsiSell": 1.0}
        assert trades[0].winning_strategy == "Momentum"
        assert trades[0].exit_winning_strategy == "RsiSell"

        # Trade 2 preserves Lot B's entry provenance while recording RsiSell exit
        assert trades[1].entry_strategy_attributions == {"TrendFollowing": 1.0}
        assert trades[1].exit_strategy_attributions == {"RsiSell": 1.0}
        assert trades[1].winning_strategy == "TrendFollowing"
        assert trades[1].exit_winning_strategy == "RsiSell"
