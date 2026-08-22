from datetime import datetime, timezone
from decimal import Decimal

import pytest

from api.interfaces.order import Order
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.database.dao.order_dao import OrderDao
from src.database.repositories.mappers.order_db_vs_entity_mapper import OrderDBVSEntityMapper

CREATED_AT = datetime(2026, 8, 22, 9, 14, 3, tzinfo=timezone.utc)


def build_dao(**overrides) -> OrderDao:
    defaults = dict(
        uuid="92121e15-0000-4000-8000-000000000001",
        provider_name="CRYPTO_DOT_COM",
        ticker_symbol="BTC_USD",
        price="63208.26661",
        quantity="0.00005",
        status=OrderStatus.COMPLETED.value,
        trade_action=TradeAction.BUY.value,
        last_updated_timestamp=CREATED_AT,
        created_timestamp=CREATED_AT,
    )
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
            status=status,
        )

        restored = OrderDBVSEntityMapper.map_to_entity(OrderDBVSEntityMapper.map_to_db(original))

        assert restored.status is status
        assert restored.uuid == original.uuid
        assert restored.trade_action is original.trade_action
        assert restored.created_time == original.created_time
