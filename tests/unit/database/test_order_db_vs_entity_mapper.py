# pylint: disable=duplicate-code
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.database.dao.order_dao import OrderDao
from src.database.repositories.mappers.order_db_vs_entity_mapper import OrderDBVSEntityMapper

CREATED_AT = datetime(2026, 8, 22, 9, 14, 3, tzinfo=timezone.utc)
EXECUTED_AT = datetime(2026, 8, 22, 9, 14, 5, tzinfo=timezone.utc)


def build_dao(**overrides) -> OrderDao:
    defaults = {
        "uuid": "92121e15-0000-4000-8000-000000000001",
        "provider_name": "CRYPTO_DOT_COM",
        "ticker_symbol": "BTC_USD",
        "price": "63208.26661",
        "quantity": "0.00005",
        "status": OrderStatus.COMPLETED.value,
        "trade_action": TradeAction.BUY.value,
        "commit_hash": "56339b9",
        "last_updated_timestamp": CREATED_AT,
        "created_timestamp": CREATED_AT,
    }
    defaults.update(overrides)
    return OrderDao(**defaults)


class TestMapToEntity:
    @pytest.mark.parametrize("status", list(OrderStatus))
    def test_preserves_every_status(self, status):
        entity = OrderDBVSEntityMapper.map_to_entity(build_dao(status=status.value))
        assert entity.status is status

    def test_null_status_falls_back_to_pending(self):
        # The column is nullable, so legacy rows can carry no status at all.
        entity = OrderDBVSEntityMapper.map_to_entity(build_dao(status=None))
        assert entity.status is OrderStatus.PENDING

    def test_unknown_status_raises_rather_than_masking_bad_data(self):
        with pytest.raises(ValueError):
            OrderDBVSEntityMapper.map_to_entity(build_dao(status="NOT_A_STATUS"))

    def test_maps_remaining_fields(self):
        entity = OrderDBVSEntityMapper.map_to_entity(build_dao())
        assert entity.uuid == "92121e15-0000-4000-8000-000000000001"
        assert entity.provider_name == "CRYPTO_DOT_COM"
        assert entity.ticker_symbol == "BTC_USD"
        assert entity.price == Decimal("63208.26661")
        assert entity.quantity == "0.00005"
        assert entity.trade_action is TradeAction.BUY
        assert entity.created_time == CREATED_AT.timestamp()
        assert entity.commit_hash == "56339b9"

    def test_null_executed_timestamp_maps_to_none(self):
        entity = OrderDBVSEntityMapper.map_to_entity(build_dao(executed_timestamp=None))
        assert entity.executed_time is None

    def test_executed_timestamp_maps_to_epoch(self):
        entity = OrderDBVSEntityMapper.map_to_entity(build_dao(executed_timestamp=EXECUTED_AT))
        assert entity.executed_time == EXECUTED_AT.timestamp()


class TestMapToDb:
    def test_null_executed_time_maps_to_none(self):
        order = Order(
            uuid="92121e15-0000-4000-8000-000000000003",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("63208.0"),
            quantity="0.001",
            trade_action=TradeAction.BUY,
            created_time=CREATED_AT.timestamp(),
            commit_hash="56339b9",
            executed_time=None,
            status=OrderStatus.PENDING,
        )
        dao = OrderDBVSEntityMapper.map_to_db(order)
        assert dao.executed_timestamp is None
        assert dao.commit_hash == "56339b9"

    def test_executed_time_maps_to_datetime(self):
        order = Order(
            uuid="92121e15-0000-4000-8000-000000000004",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("63208.0"),
            quantity="0.001",
            trade_action=TradeAction.BUY,
            created_time=CREATED_AT.timestamp(),
            commit_hash="56339b9",
            executed_time=EXECUTED_AT.timestamp(),
            status=OrderStatus.COMPLETED,
        )
        dao = OrderDBVSEntityMapper.map_to_db(order)
        assert dao.executed_timestamp == EXECUTED_AT
        assert dao.commit_hash == "56339b9"

    def test_preserves_commit_hash_on_mapping(self):
        order = Order(
            uuid="92121e15-0000-4000-8000-000000000007",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("63208.0"),
            quantity="0.001",
            trade_action=TradeAction.BUY,
            created_time=CREATED_AT.timestamp(),
            commit_hash="c4688f3b",
            status=OrderStatus.PENDING,
        )
        dao = OrderDBVSEntityMapper.map_to_db(order)
        assert dao.commit_hash == "c4688f3b"


class TestRoundTrip:
    @pytest.mark.parametrize("status", list(OrderStatus))
    def test_status_survives_entity_to_dao_and_back(self, status):
        original = Order(
            uuid="92121e15-0000-4000-8000-000000000002",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="ETH_USD",
            price=Decimal("2450.10"),
            quantity="0.01",
            trade_action=TradeAction.SELL,
            created_time=CREATED_AT.timestamp(),
            commit_hash="56339b9",
            status=status,
        )

        restored = OrderDBVSEntityMapper.map_to_entity(OrderDBVSEntityMapper.map_to_db(original))

        assert restored.status is status
        assert restored.uuid == original.uuid
        assert restored.trade_action is original.trade_action
        assert restored.created_time == original.created_time
        assert restored.commit_hash == original.commit_hash

    def test_null_executed_time_survives_round_trip(self):
        original = Order(
            uuid="92121e15-0000-4000-8000-000000000005",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="ETH_USD",
            price=Decimal("2450.10"),
            quantity="0.01",
            trade_action=TradeAction.SELL,
            created_time=CREATED_AT.timestamp(),
            commit_hash="56339b9",
            executed_time=None,
            status=OrderStatus.PENDING,
        )

        restored = OrderDBVSEntityMapper.map_to_entity(OrderDBVSEntityMapper.map_to_db(original))
        assert restored.executed_time is None
        assert restored.commit_hash == original.commit_hash

    def test_executed_time_survives_round_trip(self):
        original = Order(
            uuid="92121e15-0000-4000-8000-000000000006",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="ETH_USD",
            price=Decimal("2450.10"),
            quantity="0.01",
            trade_action=TradeAction.SELL,
            created_time=CREATED_AT.timestamp(),
            commit_hash="56339b9",
            executed_time=EXECUTED_AT.timestamp(),
            status=OrderStatus.COMPLETED,
        )

        restored = OrderDBVSEntityMapper.map_to_entity(OrderDBVSEntityMapper.map_to_db(original))
        assert restored.executed_time == original.executed_time
        assert restored.commit_hash == original.commit_hash

    def test_attribution_survives_round_trip(self):
        original = Order(
            uuid="92121e15-0000-4000-8000-000000000007",
            provider_name="CRYPTO_DOT_COM",
            ticker_symbol="BTC_USD",
            price=Decimal("63000.00"),
            quantity="0.05",
            trade_action=TradeAction.BUY,
            created_time=CREATED_AT.timestamp(),
            executed_time=EXECUTED_AT.timestamp(),
            status=OrderStatus.COMPLETED,
            decision_id="dec-12345",
            winning_strategy="TrendFollower",
            strategy_votes={"TrendFollower": "BUY", "MeanReversion": "HOLD"},
            strategy_attributions={"TrendFollower": 0.8, "Momentum": 0.2},
        )

        restored = OrderDBVSEntityMapper.map_to_entity(OrderDBVSEntityMapper.map_to_db(original))
        assert restored.decision_id == "dec-12345"
        assert restored.winning_strategy == "TrendFollower"
        assert restored.strategy_votes == {"TrendFollower": "BUY", "MeanReversion": "HOLD"}
        assert restored.strategy_attributions == {"TrendFollower": 0.8, "Momentum": 0.2}

    def test_legacy_dao_without_attribution_maps_cleanly(self):
        dao = build_dao(
            decision_id=None,
            metadata_=None,
        )
        entity = OrderDBVSEntityMapper.map_to_entity(dao)
        assert entity.decision_id is None
        assert entity.winning_strategy is None
        assert entity.strategy_votes is None
        assert entity.strategy_attributions is None

    def test_dao_with_metadata_maps_cleanly(self):
        dao = build_dao(
            decision_id="dec-123",
            metadata_={
                "winning_strategy": "TrendFollower",
                "strategy_votes": {"TrendFollower": "BUY"},
                "strategy_attributions": {"TrendFollower": 1.0},
            },
        )
        entity = OrderDBVSEntityMapper.map_to_entity(dao)
        assert entity.decision_id == "dec-123"
        assert entity.winning_strategy == "TrendFollower"
        assert entity.strategy_votes == {"TrendFollower": "BUY"}
        assert entity.strategy_attributions == {"TrendFollower": 1.0}
