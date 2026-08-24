from __future__ import annotations

import asyncio
import queue
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

from src.core.interfaces.event_bus import EventBus
from src.events.message_subscription import MessageSubscription
from src.logging.log_event import LogEvent


class LogWebSocketHandler:
    HEARTBEAT_INTERVAL_SECONDS = 30.0
    SEND_TIMEOUT_SECONDS = 5.0

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()

        subscription = MessageSubscription()
        subscription_id = self._bus.subscribe(LogEvent.EVENT_TYPE, subscription)

        try:
            await websocket.send_json(self._connected_event())
            await self._run_stream(websocket, subscription)
        except WebSocketDisconnect:
            pass
        finally:
            self._bus.unsubscribe(subscription_id)
            subscription.close()

    def _connected_event(self) -> dict:
        return {"type": "connected", "timestamp": self._now_iso()}

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
            if not await self._send_json(websocket, event.to_dict()):
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
        return {"type": "heartbeat", "timestamp": self._now_iso()}

    def _stream_status(self, dropped: int) -> dict:
        return {"type": "stream_status", "dropped": dropped, "timestamp": self._now_iso()}

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
