import hashlib
import hmac
import time
from typing import Optional

from pydantic import SecretStr

from src.configuration.exchanges_config import ExchangesConfig
from src.core.interfaces.auth_handler import AuthHandler
from src.logging.application_logging_mixin import ApplicationLoggingMixin


class CryptoDotComAuthHandler(ApplicationLoggingMixin, AuthHandler):
    def __init__(self):
        config = ExchangesConfig()
        self._api_key = config.crypto_dot_com.api_key
        self._secret_key = config.crypto_dot_com.secret_key

    def is_auth_response(self, message: dict) -> bool:
        return "method" in message and message["method"] == "public/auth"

    def get_auth_request(self) -> Optional[dict]:
        nonce = int(time.time() * 1000)
        auth_str = f"public/auth1{self._api_key}{nonce}"
        if isinstance(self._secret_key, SecretStr):
            raw_secret = self._secret_key.get_secret_value()
        else:
            raw_secret = str(self._secret_key or "")
        signature = hmac.new(
            bytes(raw_secret, "utf-8"),
            msg=bytes(auth_str, "utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        return {
            "id": 1,
            "method": "public/auth",
            "api_key": self._api_key,
            "sig": signature,
            "nonce": nonce
        }

    def handle_auth_response(self, message: dict) -> int:
        code = message["code"] if "code" in message else 0
        if code == 0:
            self.app_logger.info("Crypto.com WebSocket private connection authenticated successfully.")
        else:
            self.app_logger.error(f"Crypto.com WebSocket authentication failed: {message}")
        return code
