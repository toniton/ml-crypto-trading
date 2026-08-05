from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.asset import Asset
from src.core.managers.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.session.session_manager import SessionManager
from vcs.domain.commit import Commit


def test_session_manager_pins_commit_hash():
    session_mgr = SessionManager()
    dummy_commit_hash = "a" * 64

    # 1. Create session with pinned commit_hash
    session_mgr.create_session(session_id="test_session_01", commit_hash=dummy_commit_hash)
    assert session_mgr.current_session.commit_hash == dummy_commit_hash

    # 2. Init asset balance
    mock_asset = MagicMock(spec=Asset)
    mock_asset.key = 1
    mock_asset.ticker_symbol = "BTC_USD"
    mock_asset.exchange = ExchangeProvidersEnum.CRYPTO_DOT_COM

    session_mgr.init_asset_balance(mock_asset, starting_balance=Decimal("1000.00"))
    ctx = session_mgr.get_trading_context(1)

    # 3. Verify TradingContext has the pinned commit_hash
    assert ctx.commit_hash == dummy_commit_hash

    # 4. Verify get_session_summary includes commit_hash
    summary = session_mgr.get_session_summary(session_mgr.current_session)
    assert summary["commit_hash"] == dummy_commit_hash
    assert summary["contexts"][1]["commit_hash"] == dummy_commit_hash


def test_session_manager_auto_fetches_head_commit_hash():
    commit_hash = "b" * 64
    mock_vcs = MagicMock()
    mock_vcs.head.return_value = Commit(
        hash=commit_hash, blob_hash="0" * 64, parent_hash=None, author="toni",
        message="head", created_at=datetime.now(timezone.utc),
    )

    session_mgr = SessionManager(config_vcs=mock_vcs)
    session_mgr.create_session(session_id="auto_fetch_session")

    assert session_mgr.current_session.commit_hash == commit_hash
    mock_vcs.head.assert_called_once_with("HEAD")


def test_session_manager_explicit_hash_overrides_auto_fetch():
    mock_vcs = MagicMock()
    session_mgr = SessionManager(config_vcs=mock_vcs)
    explicit_hash = "c" * 64

    session_mgr.create_session(session_id="explicit_session", commit_hash=explicit_hash)

    assert session_mgr.current_session.commit_hash == explicit_hash
    mock_vcs.head.assert_not_called()
