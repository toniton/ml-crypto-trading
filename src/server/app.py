import asyncio
import uuid
from typing import AsyncGenerator, List, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agent import AgentGateway
from src.agent.events import AIEvent
from src.core.interfaces.conversation_store import ConversationStore
from src.core.interfaces.llm_adapter import ChatTurn
from src.server.response_reconstructor import ResponseReconstructor


class ChatRequest(BaseModel):
    prompt: Optional[str] = Field(default=None, description="Prompt query")
    query: Optional[str] = Field(default=None, description="Alternative prompt query field")
    session_id: Optional[str] = Field(
        default=None,
        description="Conversation session id. Omit to start a new session.",
    )

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
    def create(agent: AgentGateway, conversations: ConversationStore) -> FastAPI:
        app = FastAPI(title="ml-stocks-trading API", version="1.0.0")
        app.state.agent = agent
        app.state.conversations = conversations

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
            store: ConversationStore = req.app.state.conversations

            session_id = await asyncio.to_thread(store.get_or_create, chat_req.session_id)
            history: List[ChatTurn] = await asyncio.to_thread(store.history, session_id)
            await asyncio.to_thread(store.append, session_id, ChatTurn(role="user", content=prompt_text))
            message_id = uuid.uuid4().hex

            async def stream_generator() -> AsyncGenerator[str, None]:
                reconstructor = ResponseReconstructor()
                try:
                    yield ChatApp.format_event(
                        AIEvent(type="session", message_id=message_id, payload={"session_id": session_id})
                    )
                    async for event in gateway.stream(prompt_text, history=history, message_id=message_id):
                        reconstructor.feed(event)
                        yield ChatApp.format_event(event)
                except Exception as exc:  # pylint: disable=broad-except
                    error_msg = str(exc).replace("\n", " ").replace("\r", " ")
                    yield f"event: error\ndata: {error_msg}\n\n"
                finally:
                    assistant_text = reconstructor.reconstruct()
                    if assistant_text:
                        await asyncio.to_thread(
                            store.append, session_id, ChatTurn(role="assistant", content=assistant_text)
                        )

            return StreamingResponse(stream_generator(), media_type="text/event-stream")

        return app

    @staticmethod
    def format_event(event) -> str:
        name = "message"
        data = event.to_json() if hasattr(event, "to_json") else str(event)
        if hasattr(event, "type"):
            name = event.type
        return f"event: {name}\ndata: {data}\n\n"
