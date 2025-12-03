import hashlib
import hmac
import logging
import time
from typing import Optional

from src.configuration.providers.cryptodotcom_config import CryptodotcomConfig
from src.core.interfaces.auth_handler import AuthHandler


class CryptoDotComAuthHandler(AuthHandler):
    def __init__(self, config: CryptodotcomConfig = None):
        self.config = config or CryptodotcomConfig.get_instance()

    def is_auth_response(self, message: dict) -> bool:
        return message.get("method") == "public/auth"

    def get_auth_request(self) -> Optional[dict]:
        nonce = int(time.time() * 1000)
        auth_str = f"public/auth1{self.config.api_key}{nonce}"
        signature = hmac.new(
            bytes(str(self.config.secret_key), 'utf-8'),
            msg=bytes(auth_str, 'utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()

        return {
            "id": 1,
            "method": "public/auth",
            "api_key": self.config.api_key,
            "sig": signature,
            "nonce": nonce
        }

    def handle_auth_response(self, message: dict) -> int:
        logging.info("Auth response got back, IJGB!")
        pass