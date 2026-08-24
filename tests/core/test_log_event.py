import logging
import unittest

from src.core.interfaces.event import Event
from src.events.message_event import MessageEvent
from src.events.message_event_bus import CallbackSubscription, MessageEventBus
from src.logging.event_bus_log_handler import EventBusLogHandler
from src.logging.log_event import LogEvent, LogEventPayload, extract_asset_symbols


def make_payload(domain="trading", levelno=logging.INFO, asset=None, message=""):
    return LogEventPayload(
        domain=domain,
        level="INFO" if levelno == logging.INFO else "ERROR",
        level_no=levelno,
        logger=f"{domain}.test",
        message=message,
        asset=asset,
    )


class TestLogEvent(unittest.TestCase):
    def test_is_message_event_with_log_payload(self):
        event = LogEvent(make_payload(message="hello"))
        self.assertIsInstance(event, Event)
        self.assertIsInstance(event, MessageEvent)
        self.assertIsInstance(event.payload, LogEventPayload)
        self.assertEqual(event.type, "log")
        self.assertTrue(event.id)
        self.assertTrue(event.timestamp)

    def test_to_dict_envelope(self):
        event = LogEvent(make_payload(message="hello", asset="BTC_USD"))
        data = event.to_dict()
        self.assertEqual(data["type"], "log")
        self.assertEqual(data["payload"]["domain"], "trading")
        self.assertEqual(data["payload"]["level"], "INFO")
        self.assertEqual(data["payload"]["logger"], "trading.test")
        self.assertEqual(data["payload"]["message"], "hello")
        self.assertEqual(data["payload"]["asset"], "BTC_USD")
        self.assertEqual(data["metadata"], {})
        self.assertTrue(data["id"])
        self.assertTrue(data["timestamp"])
        self.assertNotIn("level_no", data["payload"])
        self.assertNotIn("thread", data["payload"])


class TestExtractAssetSymbols(unittest.TestCase):
    def test_single_symbol(self):
        self.assertEqual(extract_asset_symbols("Consensus [BTC_USD SELL]"), ["BTC_USD"])

    def test_multiple_symbols(self):
        self.assertEqual(
            extract_asset_symbols("Comparing BTC_USD with ETH_USD"),
            ["BTC_USD", "ETH_USD"],
        )

    def test_no_symbol(self):
        self.assertEqual(extract_asset_symbols("hello world"), [])


class TestEventBusLogHandler(unittest.TestCase):
    def setUp(self):
        self.bus = MessageEventBus()
        self.collected = []
        self.bus.subscribe(LogEvent.EVENT_TYPE, CallbackSubscription(self.collected.append))
        self.handler = EventBusLogHandler(self.bus)

    def test_emit_publishes_structured_event(self):
        logger = logging.getLogger("trading.emit.test")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.handlers = [self.handler]
        logger.info(
            "Consensus [BTC_USD SELL] reached",
            extra={"asset": "BTC_USD", "metadata": {"action": "SELL", "quorum": True}},
        )
        self.assertEqual(len(self.collected), 1)
        event = self.collected[0]
        self.assertIsInstance(event, LogEvent)
        self.assertEqual(event.type, "log")
        self.assertEqual(event.payload.domain, "trading")
        self.assertEqual(event.payload.level, "INFO")
        self.assertEqual(event.payload.asset, "BTC_USD")
        self.assertEqual(event.metadata, {"action": "SELL", "quorum": True})
        self.assertEqual(event.payload.message, "Consensus [BTC_USD SELL] reached")
        self.assertTrue(event.payload.thread)
        self.assertTrue(event.id)

    def test_asset_regex_fallback_single_match(self):
        logger = logging.getLogger("trading.regex.test")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.handlers = [self.handler]
        logger.info("BTC_USD crossed threshold")
        self.assertEqual(self.collected[0].payload.asset, "BTC_USD")

    def test_asset_regex_ambiguous_is_none(self):
        logger = logging.getLogger("trading.ambiguous.test")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.handlers = [self.handler]
        logger.info("Comparing BTC_USD with ETH_USD")
        self.assertIsNone(self.collected[0].payload.asset)

    def test_asset_explicit_overrides_regex(self):
        logger = logging.getLogger("trading.explicit.test")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.handlers = [self.handler]
        logger.info("Comparing BTC_USD with ETH_USD", extra={"asset": "BTC_USD"})
        self.assertEqual(self.collected[0].payload.asset, "BTC_USD")

    def test_emit_does_not_raise_on_publish_failure(self):
        logger = logging.getLogger("trading.failure.test")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.handlers = [self.handler]
        self.bus.close()
        logger.info("should not raise")
