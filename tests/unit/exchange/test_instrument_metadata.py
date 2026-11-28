from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.instrument_metadata import InstrumentMetadata
from src.backtest.backtest_rest_builder import BacktestRestBuilder
from src.backtest.backtest_rest_service import BacktestRestService
from src.exchange.clients.ccxt.ccxt_mapper import CCXTInstrumentMetadataMapper
from src.exchange.clients.cryptodotcom.cryptodotcom_rest_builder import (
    CryptoDotComRestBuilder,
)
from src.exchange.clients.cryptodotcom.mappers.cryptodotcom_mappers import (
    CryptoDotComInstrumentMetadataMapper,
)
from src.exchange.managers.rest_manager import RestManager


def test_cryptodotcom_instrument_metadata_builder_and_mapper():
    builder = CryptoDotComRestBuilder().instrument_metadata("CRO_USD")
    endpoint = builder.get_endpoint()
    assert endpoint is not None
    assert endpoint.path == "public/get-instruments"
    assert endpoint.private is False

    mapper = CryptoDotComInstrumentMetadataMapper("CRO_USD")
    payload = {
        "result": {
            "data": [
                {
                    "symbol": "BTC_USD",
                    "quantity_decimals": 4,
                    "price_decimals": 2,
                    "qty_tick_size": "0.0001",
                },
                {
                    "symbol": "CRO_USD",
                    "quantity_decimals": 0,
                    "price_decimals": 5,
                    "qty_tick_size": "1",
                    "price_tick_size": "0.00001",
                    "min_quantity": "25",
                    "min_notional": "1.0",
                },
            ]
        }
    }
    metadata = mapper.map(payload)
    assert metadata == InstrumentMetadata(
        exchange="CRYPTO_DOT_COM",
        symbol="CRO_USD",
        quantity_precision=0,
        price_precision=5,
        min_quantity=Decimal("25"),
        quantity_step=Decimal("1"),
        min_price=Decimal("0.00001"),
        min_notional=Decimal("1.0"),
    )


def test_cryptodotcom_mapper_infers_usd_min_notional_and_quote_decimals():
    mapper = CryptoDotComInstrumentMetadataMapper("CRO_USD")
    payload = {
        "result": {
            "data": [
                {
                    "symbol": "CRO_USD",
                    "base_ccy": "CRO",
                    "quote_ccy": "USD",
                    "quote_decimals": 5,
                    "quantity_decimals": 0,
                    "price_tick_size": "0.00001",
                    "qty_tick_size": "1",
                }
            ]
        }
    }
    metadata = mapper.map(payload)
    assert metadata == InstrumentMetadata(
        exchange="CRYPTO_DOT_COM",
        symbol="CRO_USD",
        quantity_precision=0,
        price_precision=5,
        min_quantity=Decimal("1"),
        quantity_step=Decimal("1"),
        min_price=Decimal("0.00001"),
        min_notional=Decimal("1.00"),
    )


def test_ccxt_instrument_metadata_mapper():
    mapper = CCXTInstrumentMetadataMapper("CCXT_BINANCE")
    metadata = mapper.map(
        {
            "symbol": "CRO/USD",
            "precision": {"amount": 0.1, "price": 0.0001},
            "limits": {
                "amount": {"min": 10},
                "cost": {"min": 5.0},
                "price": {"min": 0.0001},
            },
        }
    )
    assert metadata is not None
    assert metadata.symbol == "CRO_USD"
    assert metadata.min_quantity == Decimal("10")
    assert metadata.min_notional == Decimal("5.0")
    assert metadata.quantity_precision == 1


def test_rest_manager_get_instrument_metadata_delegates_to_service():
    manager = RestManager()
    expected = InstrumentMetadata(
        exchange="CRYPTO_DOT_COM",
        symbol="CRO_USD",
        quantity_precision=0,
        price_precision=5,
        min_quantity=Decimal("25"),
        quantity_step=Decimal("1"),
    )
    mock_service = MagicMock()
    mock_builder = MagicMock()
    mock_service.builder.return_value = mock_builder
    mock_builder.instrument_metadata.return_value = mock_builder
    mock_service.execute.return_value = expected
    manager.get_service = MagicMock(return_value=mock_service)

    result = manager.get_instrument_metadata("CRYPTO_DOT_COM", "CRO_USD")
    assert result == expected


def test_backtest_rest_service_handles_instrument_metadata():
    execution_engine = MagicMock()
    execution_engine.account = MagicMock()
    service = BacktestRestService(
        clock=MagicMock(),
        event_bus=MagicMock(),
        datasets={},
        execution_engine=execution_engine,
    )
    builder = BacktestRestBuilder().instrument_metadata("CRO_USD")
    metadata = service.execute(builder)
    assert isinstance(metadata, InstrumentMetadata)
    assert metadata.symbol == "CRO_USD"
