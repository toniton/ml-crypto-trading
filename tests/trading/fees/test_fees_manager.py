from __future__ import annotations

from unittest.mock import MagicMock

from api.interfaces.asset import Asset
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.exchange.managers.rest_manager import RestManager
from src.trading.fees.fees_manager import FeesManager


def test_init_fees_handles_exchange_error_gracefully():
    mock_rest_manager = MagicMock(spec=RestManager)
    mock_rest_manager.get_account_fees.side_effect = RuntimeError("Authentication failure")

    asset = MagicMock(spec=Asset)
    asset.exchange = ExchangeProvidersEnum.CRYPTO_DOT_COM

    manager = FeesManager(assets=[asset], rest_manager=mock_rest_manager)
    # Should not raise exception
    manager.init_fees()
    mock_rest_manager.get_account_fees.assert_called_once_with(ExchangeProvidersEnum.CRYPTO_DOT_COM.value)
