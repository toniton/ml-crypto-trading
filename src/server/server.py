import threading
from typing import Optional

import uvicorn

from src.agent import AgentGateway
from src.agent.configuration.configuration_service import ConfigurationService
from src.core.interfaces.conversation_store import ConversationStore
from src.core.interfaces.event_bus import EventBus
from src.database.database_manager import DatabaseManager
from src.server.app import ChatApp
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class ApiServer(ApplicationLoggingMixin):
    def __init__(
            self,
            agent: AgentGateway,
            conversations: ConversationStore,
            configuration_service: ConfigurationService,
            event_bus: EventBus,
            db_manager: DatabaseManager,
            host: str = "127.0.0.1",
            port: int = 8000,
    ):
        self.host = host
        self.port = port
        self.agent = agent
        self.app = ChatApp.create(
            agent=agent,
            conversations=conversations,
            configuration_service=configuration_service,
            event_bus=event_bus,
            db_manager=db_manager,
        )
        self._server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self.app_logger.warning("API Server is already running.")
            return

        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="warning"
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        self.app_logger.info("API Server started at http://%s:%s", self.host, self.port)

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=3.0)
            self.app_logger.info("API Server stopped.")
