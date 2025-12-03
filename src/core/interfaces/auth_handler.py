from abc import ABC, abstractmethod
from typing import Optional


class AuthHandler(ABC):
    @abstractmethod
    def is_auth_response(self, message: dict) -> bool:
        pass

    @abstractmethod
    def get_auth_request(self) -> Optional[dict]:
        pass

    @abstractmethod
    def handle_auth_response(self, message: dict) -> int:
        pass
