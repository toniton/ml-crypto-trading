from collections import defaultdict
from typing import Callable, Type, Dict

from backtest.events import Event


class BacktestEventBus:
    """
    Synchronous event bus for the backtesting system.
    Ensures deterministic execution by processing events immediately upon publication.
    """

    def __init__(self):
        # Dictionary mapping Event Type -> {Listener ID -> Callback}
        self._subscribers: Dict[Type[Event], Dict[int, Callable[[Event], None]]] = defaultdict(dict)
        self._id_counter: int = 0

    def subscribe(self, event_type: Type[Event], callback: Callable[[Event], None]) -> int:
        """
        Subscribe to an event type.

        Args:
            event_type: The class of the event to subscribe to.
            callback: Function to call when event is published.

        Returns:
            int: Listener ID (can be used to unsubscribe).
        """
        self._id_counter += 1
        self._subscribers[event_type][self._id_counter] = callback
        return self._id_counter

    def unsubscribe(self, listener_id: int) -> None:
        """
        Unsubscribe a listener by ID.

        Args:
            listener_id: The ID returned by subscribe().
        """
        for event_subscribers in self._subscribers.values():
            if listener_id in event_subscribers:
                del event_subscribers[listener_id]
                return

    def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers.
        Events are processed synchronously and immediately.

        Args:
            event: The event instance to publish.
        """
        event_type = type(event)
        if event_type in self._subscribers:
            # Create a shallow copy of values to allow modification/unsubscription during iteration
            callbacks = list(self._subscribers[event_type].values())
            for callback in callbacks:
                callback(event)
