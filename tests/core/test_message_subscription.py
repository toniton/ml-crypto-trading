import queue
import threading
import unittest

from src.core.interfaces.event_subscription import EventSubscription
from src.events.message_subscription import MessageSubscription
from src.logging.log_event import LogEvent, LogEventPayload


def make_event(message):
    return LogEvent(
        LogEventPayload(domain="trading", level="INFO", logger="trading.test", message=message)
    )


class TestMessageSubscription(unittest.TestCase):
    def test_implements_event_subscription(self):
        sub = MessageSubscription(max_size=3)
        self.assertIsInstance(sub, EventSubscription)

    def test_put_get_roundtrip(self):
        sub = MessageSubscription(max_size=3)
        event = make_event("hello")
        sub.put(event)
        self.assertEqual(sub.get(timeout=1.0), event)

    def test_put_from_other_thread(self):
        sub = MessageSubscription(max_size=3)
        event = make_event("from thread")
        thread = threading.Thread(target=sub.put, args=(event,))
        thread.start()
        thread.join()
        self.assertEqual(sub.get(timeout=1.0), event)

    def test_drop_oldest_and_counter(self):
        sub = MessageSubscription(max_size=3)
        events = [make_event(str(i)) for i in range(4)]
        for event in events[:3]:
            sub.put(event)
        sub.put(events[3])
        self.assertEqual(sub.get(timeout=0.5), events[1])
        self.assertEqual(sub.get(timeout=0.5), events[2])
        self.assertEqual(sub.get(timeout=0.5), events[3])
        self.assertEqual(sub.take_dropped(), 1)
        self.assertEqual(sub.take_dropped(), 0)

    def test_get_timeout_raises_empty(self):
        sub = MessageSubscription(max_size=3)
        with self.assertRaises(queue.Empty):
            sub.get(timeout=0.1)

    def test_close_unblocks_get(self):
        sub = MessageSubscription(max_size=3)
        sub.close()
        self.assertIsNone(sub.get(timeout=1.0))

    def test_put_after_close_is_ignored(self):
        sub = MessageSubscription(max_size=3)
        sub.close()
        self.assertIsNone(sub.get(timeout=1.0))
        sub.put(make_event("late"))
        with self.assertRaises(queue.Empty):
            sub.get(timeout=0.1)


if __name__ == "__main__":
    unittest.main()
