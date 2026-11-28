from unittest.mock import MagicMock

from src.agent.runtime_debug.models import RuntimeErrorEvent
from src.agent.runtime_debug.playbooks.order_validation_playbook import \
    OrderValidationPlaybook
from src.agent.runtime_debug.playbooks.playbook_resolver import \
    PlaybookResolver
from src.agent.runtime_debug.playbooks.rate_limit_playbook import \
    RateLimitPlaybook
from src.agent.runtime_debug.tools import RuntimeDebugToolbox


def test_order_validation_playbook_matches_multiple_exchanges():
    playbook = OrderValidationPlaybook()

    # Crypto.com error 213
    cdc_event = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        exchange_code=213,
        message="Invalid quantity format",
    )
    assert playbook.matches(cdc_event) is True

    # Binance LOT_SIZE error -1013
    binance_event = RuntimeErrorEvent(
        exchange="BINANCE",
        exchange_code=-1013,
        message="Filter failure: LOT_SIZE",
    )
    assert playbook.matches(binance_event) is True

    # Generic keyword match
    generic_event = RuntimeErrorEvent(
        exchange="KRAKEN",
        message="Order rejected: minimum precision violation",
    )
    assert playbook.matches(generic_event) is True

    # HTTP 400 on execute_order
    http_event = RuntimeErrorEvent(
        http_status=400,
        operation="execute_order",
        message="Bad Request",
    )
    assert playbook.matches(http_event) is True


def test_order_validation_playbook_investigation_finds_precision_violation():
    playbook = OrderValidationPlaybook()
    toolbox = MagicMock(spec=RuntimeDebugToolbox)
    toolbox.get_exchange_instrument_metadata.return_value = {
        "exchange": "CRYPTO_DOT_COM",
        "symbol": "BTC_USD",
        "quantity_precision": 4,
        "min_quantity": "0.0001",
        "quantity_step": "0.0001",
    }
    toolbox.get_last_successful_order_commit.return_value = "commit_success_123"
    toolbox.get_configuration_diff.return_value = {"diff": "some config changes"}

    event = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        exchange_code=213,
        message="Invalid quantity format",
        asset="BTC_USD",
        commit_hash="commit_fail_456",
        metadata={"order_quantity": "0.000078"},
    )

    evidence = playbook.investigate(event, toolbox)
    assert len(evidence) == 3

    # Rule evidence
    assert evidence[0].source == "exchange_metadata"

    # Validation failure evidence
    assert evidence[1].source == "order_validation_analysis"
    assert evidence[1].data["violates_precision"] is True
    assert evidence[1].data["violates_min_quantity"] is True
    assert evidence[1].data["actual_decimals"] == 6

    # VCS Diff evidence
    assert evidence[2].source == "vcs_history"
    assert evidence[2].data["last_successful_commit"] == "commit_success_123"


def test_playbook_resolver_selects_correct_playbook():
    resolver = PlaybookResolver()

    cdc_event = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        exchange_code=213,
        message="Invalid quantity format",
    )
    cdc_playbook = resolver.resolve(cdc_event)
    assert isinstance(cdc_playbook, OrderValidationPlaybook)

    binance_event = RuntimeErrorEvent(
        exchange="BINANCE",
        exchange_code=-1013,
        message="Filter failure: LOT_SIZE",
    )
    binance_playbook = resolver.resolve(binance_event)
    assert isinstance(binance_playbook, OrderValidationPlaybook)

    rate_limit_event = RuntimeErrorEvent(
        http_status=429,
        message="Too many requests",
    )
    rl_playbook = resolver.resolve(rate_limit_event)
    assert isinstance(rl_playbook, RateLimitPlaybook)

    unknown_event = RuntimeErrorEvent(
        component="some_unknown_service",
        message="weird internal error",
    )
    assert resolver.resolve(unknown_event) is None


def test_order_validation_playbook_matches_cryptodotcom_415_http_500():
    playbook = OrderValidationPlaybook()
    event = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        exchange_code=415,
        http_status=500,
        operation="execute_order",
        asset="CRO_USD",
        message="BELOW_MIN_ORDER_SIZE",
    )
    assert playbook.matches(event) is True


def test_order_validation_playbook_uses_live_exchange_metadata_and_computes_min_qty():
    from decimal import Decimal

    from api.interfaces.instrument_metadata import InstrumentMetadata

    rest_manager = MagicMock()
    rest_manager.get_instrument_metadata.return_value = InstrumentMetadata(
        exchange="CRYPTO_DOT_COM",
        symbol="CRO_USD",
        quantity_precision=0,
        price_precision=5,
        min_quantity=Decimal("25"),
        quantity_step=Decimal("1"),
        min_price=Decimal("0.00001"),
        min_notional=Decimal("1.00"),
    )
    toolbox = RuntimeDebugToolbox(rest_manager=rest_manager)
    playbook = OrderValidationPlaybook()
    event = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        exchange_code=415,
        http_status=500,
        operation="execute_order",
        asset="CRO_USD",
        message="BELOW_MIN_ORDER_SIZE",
        metadata={"order_quantity": "19", "order_price": "0.040180"},
    )

    evidence = playbook.investigate(event, toolbox)

    rest_manager.get_instrument_metadata.assert_called_once_with("CRYPTO_DOT_COM", "CRO_USD")
    assert evidence[0].data["source"] == "exchange_api"
    analysis = evidence[1].data
    assert analysis["violates_min_quantity"] is True
    assert analysis["violates_min_notional"] is True
    assert analysis["exchange_reported_min_order_size"] is True
    assert analysis["recommended_min_quantity"] == "25"


def test_toolbox_falls_back_to_static_metadata_when_exchange_api_fails():
    rest_manager = MagicMock()
    rest_manager.get_instrument_metadata.side_effect = RuntimeError("exchange unreachable")
    toolbox = RuntimeDebugToolbox(rest_manager=rest_manager)

    rules = toolbox.get_exchange_instrument_metadata("CRYPTO_DOT_COM", "BTC_USD")

    assert rules["source"] == "static_fallback"
    assert rules["min_quantity"] == "0.0001"


def test_order_validation_playbook_recommends_above_rejected_qty_for_cro_usd():
    from decimal import Decimal

    from api.interfaces.instrument_metadata import InstrumentMetadata

    rest_manager = MagicMock()
    rest_manager.get_instrument_metadata.return_value = InstrumentMetadata(
        exchange="CRYPTO_DOT_COM",
        symbol="CRO_USD",
        quantity_precision=0,
        price_precision=5,
        min_quantity=Decimal("1"),
        quantity_step=Decimal("1"),
        min_price=Decimal("0.00001"),
        min_notional=Decimal("1.00"),
    )
    toolbox = RuntimeDebugToolbox(rest_manager=rest_manager)
    playbook = OrderValidationPlaybook()
    event = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        exchange_code=415,
        http_status=500,
        operation="execute_order",
        asset="CRO_USD",
        message="BELOW_MIN_ORDER_SIZE",
        metadata={"order_quantity": "19", "order_price": "0.039990"},
    )

    evidence = playbook.investigate(event, toolbox)
    analysis = evidence[1].data
    assert analysis["recommended_min_quantity"] == "26"
    assert analysis["violates_min_notional"] is True


def test_order_validation_playbook_never_recommends_below_rejected_qty_without_notional():
    from decimal import Decimal

    from api.interfaces.instrument_metadata import InstrumentMetadata

    rest_manager = MagicMock()
    rest_manager.get_instrument_metadata.return_value = InstrumentMetadata(
        exchange="CRYPTO_DOT_COM",
        symbol="CRO_USD",
        quantity_precision=0,
        price_precision=5,
        min_quantity=Decimal("1"),
        quantity_step=Decimal("1"),
        min_price=Decimal("0.00001"),
        min_notional=None,
    )
    toolbox = RuntimeDebugToolbox(rest_manager=rest_manager)
    playbook = OrderValidationPlaybook()
    event = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        exchange_code=415,
        http_status=500,
        operation="execute_order",
        asset="CRO_USD",
        message="BELOW_MIN_ORDER_SIZE",
        metadata={"order_quantity": "19", "order_price": "0.039990"},
    )

    evidence = playbook.investigate(event, toolbox)
    assert evidence[1].data["recommended_min_quantity"] == "20"


def test_playbook_resolver_routes_insufficient_balance_away_from_order_validation():
    resolver = PlaybookResolver()
    event = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        exchange_code=306,
        http_status=500,
        operation="execute_order",
        asset="CRO_USD",
        message="INSUFFICIENT_AVAILABLE_BALANCE",
    )
    playbook = resolver.resolve(event)
    assert playbook is not None
    assert playbook.name == "insufficient_balance"
    assert OrderValidationPlaybook().matches(event) is False


def test_insufficient_balance_playbook_sell_recommends_pausing_asset():
    from decimal import Decimal

    from api.interfaces.account_balance import AccountBalance
    from api.interfaces.instrument_metadata import InstrumentMetadata
    from src.agent.runtime_debug.playbooks.insufficient_balance_playbook import \
        InsufficientBalancePlaybook

    rest_manager = MagicMock()
    rest_manager.get_instrument_metadata.return_value = InstrumentMetadata(
        exchange="CRYPTO_DOT_COM",
        symbol="CRO_USD",
        quantity_precision=0,
        price_precision=5,
        min_quantity=Decimal("1"),
        quantity_step=Decimal("1"),
        min_price=Decimal("0.00001"),
        min_notional=Decimal("1.00"),
    )
    rest_manager.get_account_balance.return_value = [
        AccountBalance(currency="CRO", available_balance=Decimal("30"))
    ]
    rest_manager.get_open_orders.return_value = []

    toolbox = RuntimeDebugToolbox(rest_manager=rest_manager)
    playbook = InsufficientBalancePlaybook()
    event = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        exchange_code=306,
        http_status=500,
        operation="execute_order",
        asset="CRO_USD",
        message="INSUFFICIENT_AVAILABLE_BALANCE",
        metadata={"trade_action": "SELL", "order_quantity": "47", "order_price": "0.039970"},
    )

    evidence = playbook.investigate(event, toolbox)
    analysis = evidence[1].data
    assert analysis["min_quantity"] == "1"
    assert analysis["available_balance"] == "30"
    assert analysis["is_sell_dust"] is False
    assert analysis["remediation_action"] == "pause_asset"
    assert analysis["proposed_changes"][0]["path"] == "assets.CRO_USD.enabled"
    assert analysis["proposed_changes"][0]["new_value"] is False


def test_insufficient_balance_playbook_transient_sell_dust_avoids_disabling_asset():
    from decimal import Decimal

    from api.interfaces.account_balance import AccountBalance
    from api.interfaces.instrument_metadata import InstrumentMetadata
    from src.agent.runtime_debug.nodes.diagnose_node import DiagnoseNode
    from src.agent.runtime_debug.nodes.generate_suggestion_node import \
        GenerateSuggestionNode
    from src.agent.runtime_debug.playbooks.insufficient_balance_playbook import \
        InsufficientBalancePlaybook

    rest_manager = MagicMock()
    rest_manager.get_instrument_metadata.return_value = InstrumentMetadata(
        exchange="CRYPTO_DOT_COM",
        symbol="CRO_USD",
        quantity_precision=0,
        price_precision=5,
        min_quantity=Decimal("1"),
        quantity_step=Decimal("1"),
        min_price=Decimal("0.00001"),
        min_notional=Decimal("1.00"),
    )
    rest_manager.get_account_balance.return_value = [
        AccountBalance(currency="CRO", available_balance=Decimal("21.5912"))
    ]
    rest_manager.get_open_orders.return_value = []

    toolbox = RuntimeDebugToolbox(rest_manager=rest_manager)
    playbook = InsufficientBalancePlaybook()
    event = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        exchange_code=306,
        http_status=500,
        operation="execute_order",
        asset="CRO_USD",
        message="INSUFFICIENT_AVAILABLE_BALANCE",
        metadata={
            "trade_action": "SELL",
            "order_quantity": "26",
            "order_price": "0.039638",
            "occurrence_count": 1,
        },
    )

    evidence = playbook.investigate(event, toolbox)
    analysis = evidence[1].data
    assert analysis["is_sell_dust"] is True
    assert analysis["remediation_action"] == "reconcile_balance_dust"
    assert analysis["proposed_changes"] == []

    diagnosis = DiagnoseNode()({"error_event": event, "evidence": evidence})["diagnosis"]
    assert "dust" in diagnosis.summary.lower()
    assert "min_notional=1.00" in diagnosis.suspected_root_cause

    suggestion = GenerateSuggestionNode()(
        {"error_event": event, "evidence": evidence, "diagnosis": diagnosis}
    )["suggestion"]
    assert suggestion.requires_configuration_change is False
    assert suggestion.affected_component == "trading.accounts.account_manager"
    assert "no config change" in suggestion.summary.lower()


def test_insufficient_balance_playbook_repeated_sell_dust_still_pauses_asset():
    from decimal import Decimal

    from api.interfaces.account_balance import AccountBalance
    from api.interfaces.instrument_metadata import InstrumentMetadata
    from src.agent.runtime_debug.playbooks.insufficient_balance_playbook import \
        InsufficientBalancePlaybook

    rest_manager = MagicMock()
    rest_manager.get_instrument_metadata.return_value = InstrumentMetadata(
        exchange="CRYPTO_DOT_COM",
        symbol="CRO_USD",
        quantity_precision=0,
        price_precision=5,
        min_quantity=Decimal("1"),
        quantity_step=Decimal("1"),
        min_price=Decimal("0.00001"),
        min_notional=Decimal("1.00"),
    )
    rest_manager.get_account_balance.return_value = [
        AccountBalance(currency="CRO", available_balance=Decimal("21.5912"))
    ]
    rest_manager.get_open_orders.return_value = []

    toolbox = RuntimeDebugToolbox(rest_manager=rest_manager)
    playbook = InsufficientBalancePlaybook()
    event = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        exchange_code=306,
        http_status=500,
        operation="execute_order",
        asset="CRO_USD",
        message="INSUFFICIENT_AVAILABLE_BALANCE",
        metadata={
            "trade_action": "SELL",
            "order_quantity": "26",
            "order_price": "0.039638",
            "occurrence_count": 3,
        },
    )

    evidence = playbook.investigate(event, toolbox)
    analysis = evidence[1].data
    assert analysis["is_sell_dust"] is True
    assert analysis["remediation_action"] == "pause_asset"
    assert analysis["proposed_changes"][0]["path"] == "assets.CRO_USD.enabled"
    assert analysis["proposed_changes"][0]["new_value"] is False


def test_insufficient_balance_playbook_buy_with_partial_capital_tightens_exposure():
    from decimal import Decimal

    from api.interfaces.account_balance import AccountBalance
    from api.interfaces.instrument_metadata import InstrumentMetadata
    from src.agent.runtime_debug.playbooks.insufficient_balance_playbook import \
        InsufficientBalancePlaybook

    rest_manager = MagicMock()
    rest_manager.get_instrument_metadata.return_value = InstrumentMetadata(
        exchange="CRYPTO_DOT_COM",
        symbol="DOGE_USD",
        quantity_precision=0,
        price_precision=5,
        min_quantity=Decimal("1"),
        quantity_step=Decimal("1"),
        min_price=Decimal("0.00001"),
        min_notional=Decimal("1.00"),
    )
    rest_manager.get_account_balance.return_value = [
        AccountBalance(currency="USD", available_balance=Decimal("5.00"))
    ]
    rest_manager.get_open_orders.return_value = []

    toolbox = RuntimeDebugToolbox(rest_manager=rest_manager)
    playbook = InsufficientBalancePlaybook()
    event = RuntimeErrorEvent(
        exchange="CRYPTO_DOT_COM",
        exchange_code=306,
        http_status=500,
        operation="execute_order",
        asset="DOGE_USD",
        message="INSUFFICIENT_AVAILABLE_BALANCE",
        metadata={"trade_action": "BUY", "order_quantity": "100", "order_price": "0.15"},
    )

    evidence = playbook.investigate(event, toolbox)
    analysis = evidence[1].data
    assert analysis["remediation_action"] == "reduce_exposure"
    assert analysis["proposed_changes"][0]["path"] == "assets.DOGE_USD.portfolio.max_exposure_pct"
    assert 0.05 <= analysis["proposed_changes"][0]["new_value"] <= 0.50
