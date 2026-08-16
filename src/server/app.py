from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agent import AgentGateway


class ChatRequest(BaseModel):
    prompt: Optional[str] = Field(default=None, description="Prompt query")
    query: Optional[str] = Field(default=None, description="Alternative prompt query field")

    def get_prompt_text(self) -> str:  # pylint: disable=no-member
        prompt_val = getattr(self, "prompt", None)
        query_val = getattr(self, "query", None)
        raw = prompt_val if isinstance(prompt_val, str) else query_val
        if not isinstance(raw, str) or not raw.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either 'prompt' or 'query' must be provided."
            )
        return raw.strip()


class ChatApp:
    """Builds and formats the FastAPI application exposing the agent gateway."""

    @staticmethod
    def create(agent: Optional[AgentGateway] = None) -> FastAPI:
        app = FastAPI(title="ml-stocks-trading API", version="1.0.0")
        app.state.agent = agent

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.post("/api/v1/chat")
        async def chat_endpoint(chat_req: ChatRequest, req: Request) -> StreamingResponse:
            gateway: Optional[AgentGateway] = getattr(req.app.state, "agent", None)
            if not gateway:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Agent is not configured."
                )

            prompt_text = chat_req.get_prompt_text()

            async def stream_generator() -> AsyncGenerator[str, None]:
                try:
                    async for event in gateway.stream(prompt_text):
                        yield ChatApp.format_event(event)
                except Exception as exc:  # pylint: disable=broad-except
                    error_msg = str(exc).replace("\n", " ").replace("\r", " ")
                    yield f"event: error\ndata: {error_msg}\n\n"

            return StreamingResponse(stream_generator(), media_type="text/event-stream")

        return app

    @staticmethod
    def format_event(event) -> str:
        name = "message"
        data = event.to_json() if hasattr(event, "to_json") else str(event)
        if hasattr(event, "type"):
            name = event.type
        return f"event: {name}\ndata: {data}\n\n"
