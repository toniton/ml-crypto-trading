import asyncio
import json
from queue import Queue

import uvicorn
from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect


class WebServer:

    def __init__(self, activity_queue: Queue):
        self.app = FastAPI()
        self.activity_queue = activity_queue
        self.app.state.q = activity_queue
        self.init_routes()
        self.config = uvicorn.Config(self.app, port=5555, log_level="info")
        self.server = uvicorn.Server(self.config)

    def init_routes(self):
        @self.app.get("/")
        async def get():
            return "Hello"

        @self.app.websocket("/ws")
        async def listen_socket(websocket: WebSocket):
            await websocket.accept()
            try:
                while True:
                    if not websocket.app.state.q.empty():
                        activity = websocket.app.state.q.get_nowait()
                        await websocket.send_json({"event": {"type": "New activity", "payload": json.loads(activity)}})
                    else:
                        await asyncio.sleep(0.1)
            except WebSocketDisconnect as exc:
                print(exc)

        @self.app.get("/items/")
        def read_items():
            return [{"name": "Empanada"}, {"name": "Arepa"}]

    def run(self):
        self.server.run()
