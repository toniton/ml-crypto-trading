from typing import Any
from urllib.request import Request


class RequestHelper:
    @staticmethod
    def init_http_connection(base_url: str, path: str, method: str = "GET", data: Any = None, headers: dict = None) -> Request:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            **(headers or {})
        }
        request = Request(url=base_url + path, method=method, headers=headers, data=data)
        return request
