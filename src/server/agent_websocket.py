from __future__ import annotations

import asyncio
import queue
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

from src.core.interfaces.event_bus import EventBus
from src.events.agent_events import (
    AgentActionCompletedEvent,
    AgentActionCreatedEvent,
    AgentActionFailedEvent,
    AgentActionUpdatedEvent,
    AgentApprovalRequestedEvent,
    AgentApprovalResolvedEvent,
    AgentMessageCreatedEvent,
)
from src.events.message_subscription import MessageSubscription


class AgentWebSocketHandler:
    HEARTBEAT_INTERVAL_SECONDS = 30.0
    SEND_TIMEOUT_SECONDS = 5.0

    AGENT_EVENT_TYPES = [
        AgentMessageCreatedEvent.EVENT_TYPE,
        "AgentMessageCreatedEvent",
        AgentActionCreatedEvent.EVENT_TYPE,
        "AgentActionCreatedEvent",
        AgentActionUpdatedEvent.EVENT_TYPE,
        "AgentActionUpdatedEvent",
        AgentApprovalRequestedEvent.EVENT_TYPE,
        "AgentApprovalRequestedEvent",
        AgentApprovalResolvedEvent.EVENT_TYPE,
        "AgentApprovalResolvedEvent",
        AgentActionCompletedEvent.EVENT_TYPE,
        "AgentActionCompletedEvent",
        AgentActionFailedEvent.EVENT_TYPE,
        "AgentActionFailedEvent",
    ]

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()

        subscription = MessageSubscription()
        sub_ids = [self._bus.subscribe(event_type, subscription) for event_type in self.AGENT_EVENT_TYPES]

        try:
            await websocket.send_json(self._connected_event())
            await self._run_stream(websocket, subscription)
        except WebSocketDisconnect:
            pass
        finally:
            for sub_id in sub_ids:
                self._bus.unsubscribe(sub_id)
            subscription.close()

    def _connected_event(self) -> dict:
        return {"type": "connected", "channel": "agent", "timestamp": self._now_iso()}

    async def _run_stream(self, websocket: WebSocket, subscription: MessageSubscription) -> None:
        pump_task = asyncio.create_task(self._pump(websocket, subscription))
        receive_task = asyncio.create_task(self._receive_loop(websocket))
        done, pending = await asyncio.wait(
            {receive_task, pump_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in done:
            try:
                task.result()
            except WebSocketDisconnect:
                pass

        for task in pending:
            task.cancel()

    @staticmethod
    async def _receive_loop(websocket: WebSocket) -> None:
        try:
            while True:
                message = await websocket.receive_text()
                if message == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            return

    async def _pump(self, websocket: WebSocket, subscription: MessageSubscription) -> None:
        while True:
            try:
                event = await asyncio.to_thread(
                    subscription.get, self.HEARTBEAT_INTERVAL_SECONDS
                )
            except queue.Empty:
                if not await self._send_json(websocket, self._heartbeat(subscription)):
                    return
                continue
            if event is None:
                return

            event_dict = event.to_dict()
            event_dict["event_name"] = event.EVENT_TYPE or event.type or "agent_event"
            if "payload" in event_dict and isinstance(event_dict["payload"], dict):
                for k, v in event_dict["payload"].items():
                    event_dict.setdefault(k, v)
            if not await self._send_json(websocket, event_dict):
                return
            dropped = subscription.take_dropped()
            if dropped > 0 and not await self._send_json(websocket, self._stream_status(dropped)):
                return

    async def _send_json(self, websocket: WebSocket, payload) -> bool:
        try:
            await asyncio.wait_for(websocket.send_json(payload), timeout=self.SEND_TIMEOUT_SECONDS)
            return True
        except (asyncio.TimeoutError, WebSocketDisconnect, RuntimeError):
            return False

    def _heartbeat(self, subscription: MessageSubscription) -> dict:
        dropped = subscription.take_dropped()
        if dropped > 0:
            return self._stream_status(dropped)
        return {"type": "heartbeat", "channel": "agent", "timestamp": self._now_iso()}

    def _stream_status(self, dropped: int) -> dict:
        return {"type": "stream_status", "dropped": dropped, "timestamp": self._now_iso()}

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
