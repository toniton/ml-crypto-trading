import asyncio
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, List, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agent import AgentGateway, ProposalDecision
from src.agent.cache.cached_proposal_store import CachedProposalStore
from src.agent.configuration.configuration_service import ConfigurationService
from src.agent.events import AIEvent
from src.core.interfaces.conversation_store import ConversationMessage, ConversationStore
from src.core.interfaces.event_bus import EventBus
from src.core.interfaces.llm_adapter import ChatTurn
from src.core.interfaces.proposal_store import ProposalStore
from src.server.log_websocket import LogWebSocketHandler
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


class ProposalDecisionRequest(BaseModel):
    action: ProposalDecision = Field(description="Decision to take on the pending proposal.")


class ChatApp:
    """Builds and formats the FastAPI application exposing the agent gateway."""

    @staticmethod
    def create(
            agent: AgentGateway,
            conversations: ConversationStore,
            configuration_service: ConfigurationService,
            event_bus: EventBus,
    ) -> FastAPI:
        app = FastAPI(title="ml-stocks-trading API", version="1.0.0")
        app.state.agent = agent
        app.state.conversations = conversations
        app.state.configuration_service = configuration_service
        app.state.proposal_store = CachedProposalStore(conversations=conversations)

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        log_handler = LogWebSocketHandler(event_bus)

        @app.websocket("/api/v1/logs/ws")
        async def log_websocket(websocket: WebSocket) -> None:
            await log_handler.handle(websocket)

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
            proposal_store: Optional[ProposalStore] = req.app.state.proposal_store

            session_id = await asyncio.to_thread(store.get_or_create, chat_req.session_id)
            history: List[ChatTurn] = await asyncio.to_thread(store.history, session_id)
            message_id = uuid.uuid4().hex
            await asyncio.to_thread(
                store.append,
                session_id,
                ConversationMessage(role="user", content=prompt_text, message_id=message_id),
            )

            async def stream_generator() -> AsyncGenerator[str, None]:
                reconstructor = ResponseReconstructor()
                blocks: list = []
                tokens: List[str] = []
                proposal = None
                try:
                    yield ChatApp.format_event(
                        AIEvent(type="session", message_id=message_id, payload={"session_id": session_id})
                    )
                    async for event in gateway.stream(prompt_text, history=history, message_id=message_id):
                        reconstructor.feed(event)
                        ChatApp._capture(event, blocks, tokens)
                        if event.type == "done":
                            payload = event.payload if isinstance(event.payload, dict) else {}
                            if payload.get("proposal") is not None:
                                proposal = payload["proposal"]
                                if proposal_store is not None:
                                    proposal_store.register(message_id, proposal)
                        yield ChatApp.format_event(event)
                except Exception as exc:  # pylint: disable=broad-except
                    error_msg = str(exc).replace("\n", " ").replace("\r", " ")
                    yield f"event: error\ndata: {error_msg}\n\n"
                finally:
                    assistant_text = reconstructor.reconstruct()
                    if assistant_text:
                        payload = {"blocks": blocks, "tokens": "".join(tokens)} if blocks or tokens else None
                        if proposal is not None:
                            payload = payload or {}
                            payload["proposal"] = (
                                proposal.model_dump(mode="json")
                                if hasattr(proposal, "model_dump")
                                else proposal
                            )
                        await asyncio.to_thread(
                            store.append,
                            session_id,
                            ConversationMessage(
                                role="assistant",
                                content=assistant_text,
                                message_id=message_id,
                                payload=payload,
                            ),
                        )

            return StreamingResponse(stream_generator(), media_type="text/event-stream")

        @app.get("/api/v1/sessions")
        async def list_sessions_endpoint(req: Request):
            store: ConversationStore = req.app.state.conversations
            sessions = await asyncio.to_thread(store.list_sessions)
            return [session.model_dump(mode="json") for session in sessions]

        @app.get("/api/v1/sessions/{session_id}")
        async def get_session_endpoint(session_id: str, req: Request):
            store: ConversationStore = req.app.state.conversations
            messages = await asyncio.to_thread(store.messages, session_id)
            return {
                "session_id": session_id,
                "messages": [message.model_dump(mode="json") for message in messages],
            }

        @app.post("/api/v1/proposals/{message_id}/decision")
        async def decide_proposal_endpoint(message_id: str, decision: ProposalDecisionRequest, req: Request):
            configuration_service: ConfigurationService = req.app.state.configuration_service
            proposal_store: ProposalStore = req.app.state.proposal_store
            store: ConversationStore = req.app.state.conversations

            proposal = await asyncio.to_thread(proposal_store.get, message_id)
            if proposal is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No pending proposal for message '{message_id}'.",
                )

            if decision.action == ProposalDecision.REJECT:
                await asyncio.to_thread(proposal_store.remove, message_id)
                await ChatApp._record_decision(store, message_id, proposal, ProposalDecision.REJECT)
                return {"action": decision.action.value, "message_id": message_id}

            validation = await asyncio.to_thread(configuration_service.validate_proposal, proposal)
            if not validation.valid:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"errors": validation.errors},
                )

            commit, warnings = await asyncio.to_thread(
                configuration_service.apply_proposal_to_vcs, proposal
            )
            await asyncio.to_thread(proposal_store.remove, message_id)
            await ChatApp._record_decision(
                store, message_id, proposal, ProposalDecision.APPROVE, commit_hash=commit.hash
            )

            return {
                "action": decision.action.value,
                "message_id": message_id,
                "commit_hash": commit.hash,
                "summary": proposal.summary,
                "warnings": warnings,
            }

        return app

    @staticmethod
    def format_event(event) -> str:
        name = "message"
        data = event.to_json() if hasattr(event, "to_json") else str(event)
        if hasattr(event, "type"):
            name = event.type
        return f"event: {name}\ndata: {data}\n\n"

    @staticmethod
    def _capture(event, blocks: list, tokens: List[str]) -> None:
        if event.type == "block":
            payload = event.payload
            blocks.append(payload.model_dump() if hasattr(payload, "model_dump") else payload)
        elif event.type == "clarification":
            payload = event.payload or {}
            if isinstance(payload, dict):
                blocks.append(
                    {
                        "type": "clarification",
                        "content": payload.get("question", ""),
                        "intent": payload.get("intent"),
                    }
                )
        elif event.type == "token" and isinstance(event.payload, str):
            tokens.append(event.payload)

    @staticmethod
    async def _record_decision(
            store: ConversationStore,
            message_id: str,
            proposal,
            action: ProposalDecision,
            commit_hash: Optional[str] = None,
    ) -> None:
        message = await asyncio.to_thread(store.get_message, message_id)
        session_id = message.conversation_id if message else None
        if not session_id:
            return

        decision_data: dict = {
            "action": action.value,
            "proposal_message_id": message_id,
            "summary": proposal.summary,
            "decided_at": datetime.now(timezone.utc).isoformat(),
        }
        if commit_hash:
            decision_data["commit_hash"] = commit_hash

        await asyncio.to_thread(
            store.append,
            session_id,
            ConversationMessage(
                role="assistant",
                content=f"{action.label} configuration change: {proposal.summary}",
                message_id=message_id,
                payload={"decision": decision_data},
            ),
        )
