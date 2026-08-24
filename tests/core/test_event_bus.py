import unittest
from dataclasses import dataclass

from src.core.interfaces.event import Event
from src.core.interfaces.event_bus import EventBus
from src.events.message_event import MessageEvent
from src.events.message_event_bus import CallbackSubscription, MessageEventBus


class TestMessageEvent(unittest.TestCase):
    def test_implements_event(self):
        self.assertIsInstance(MessageEvent("log", {}), Event)

    def test_to_dict_shape(self):
        event = MessageEvent("log", {"message": "hello"})
        data = event.to_dict()
        self.assertEqual(data["type"], "log")
        self.assertEqual(data["payload"], {"message": "hello"})
        self.assertTrue(data["id"])
        self.assertTrue(data["timestamp"])

    def test_dataclass_payload_serialized(self):
        @dataclass
        class Payload:
            value: int = 0

        event = MessageEvent("x", Payload(value=42))
        self.assertEqual(event.to_dict()["payload"], {"value": 42})

    def test_payload_with_to_dict_wins(self):
        class Payload:
            def to_dict(self):
                return {"custom": True}

        event = MessageEvent("x", Payload())
        self.assertEqual(event.to_dict()["payload"], {"custom": True})

    def test_id_unique(self):
        self.assertNotEqual(MessageEvent("a", None).id, MessageEvent("a", None).id)


class TestMessageEventBus(unittest.TestCase):
    def test_implements_event_bus(self):
        self.assertIsInstance(MessageEventBus(), EventBus)

    def test_routes_by_type(self):
        bus = MessageEventBus()
        collected = []
        bus.subscribe("log", CallbackSubscription(collected.append))
        bus.publish(MessageEvent("other", None))
        bus.publish(MessageEvent("log", None))
        self.assertEqual(len(collected), 1)
        self.assertEqual(collected[0].type, "log")

    def test_multiple_handlers_same_type(self):
        bus = MessageEventBus()
        first, second = [], []
        bus.subscribe("order_placed", CallbackSubscription(first.append))
        bus.subscribe("order_placed", CallbackSubscription(second.append))
        event = MessageEvent("order_placed", {"n": 1})
        bus.publish(event)
        self.assertEqual(first, [event])
        self.assertEqual(second, [event])

    def test_unsubscribe(self):
        bus = MessageEventBus()
        collected = []
        subscription_id = bus.subscribe("log", CallbackSubscription(collected.append))
        bus.unsubscribe(subscription_id)
        bus.publish(MessageEvent("log", None))
        self.assertEqual(collected, [])

    def test_subscriber_count(self):
        bus = MessageEventBus()
        subscription_id = bus.subscribe("log", CallbackSubscription(lambda _event: None))
        bus.subscribe("other", CallbackSubscription(lambda _event: None))
        self.assertEqual(bus.subscriber_count("log"), 1)
        self.assertEqual(bus.subscriber_count(), 2)
        bus.unsubscribe(subscription_id)
        self.assertEqual(bus.subscriber_count("log"), 0)

    def test_handler_decorator(self):
        bus = MessageEventBus()
        collected = []

        @bus.handler("order_placed")
        def on_order(event):
            collected.append(event)

        bus.publish(MessageEvent("order_placed", {"x": 1}))
        self.assertEqual(len(collected), 1)
        self.assertEqual(collected[0].payload, {"x": 1})

    def test_bad_callback_does_not_break_others(self):
        bus = MessageEventBus()
        collected = []

        def bad_callback(_event):
            raise RuntimeError("boom")

        bus.subscribe("log", CallbackSubscription(bad_callback))
        bus.subscribe("log", CallbackSubscription(collected.append))
        bus.publish(MessageEvent("log", None))
        self.assertEqual(len(collected), 1)

    def test_close_clears_subscribers(self):
        bus = MessageEventBus()
        bus.subscribe("log", CallbackSubscription(lambda _event: None))
        bus.close()
        self.assertEqual(bus.subscriber_count(), 0)
