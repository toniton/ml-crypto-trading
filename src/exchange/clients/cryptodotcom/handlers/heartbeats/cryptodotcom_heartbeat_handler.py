from typing import Optional

from src.core.interfaces.heartbeat_handler import HeartbeatHandler


class CryptoDotComHeartbeatHandler(HeartbeatHandler):
    def is_heartbeat(self, message: dict) -> bool:
        return message.get("method") == "public/heartbeat"

    def get_heartbeat_response(self, message: dict) -> Optional[dict]:
        return {
            "id": message.get("id"),
            "method": "public/respond-heartbeat"
        }

    def get_heartbeat_timeout(self) -> int:
        return 30
