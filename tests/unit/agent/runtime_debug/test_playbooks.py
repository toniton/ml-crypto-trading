from unittest.mock import MagicMock

from src.agent.runtime_debug.models import RuntimeErrorEvent
from src.agent.runtime_debug.playbooks.order_validation_playbook import OrderValidationPlaybook
from src.agent.runtime_debug.playbooks.playbook_resolver import PlaybookResolver
from src.agent.runtime_debug.playbooks.rate_limit_playbook import RateLimitPlaybook
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
