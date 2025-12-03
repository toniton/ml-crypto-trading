from abc import ABC, abstractmethod
from typing import Optional


class HeartbeatHandler(ABC):
    @abstractmethod
    def is_heartbeat(self, message: dict) -> bool:
        pass

    @abstractmethod
    def get_heartbeat_response(self, message: dict) -> Optional[dict]:
        pass

    @abstractmethod
    def get_heartbeat_timeout(self) -> int:
        pass
