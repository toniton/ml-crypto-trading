import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.core.logging.application_logging_mixin import ApplicationLoggingMixin


class RequestHelper(ApplicationLoggingMixin):
    @classmethod
    def create_request(
            cls,
            base_url: str,
            path: str,
            method: str = "GET",
            data: Any = None,
            headers: dict[str, str] = None
    ) -> Request:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            **(headers or {})
        }
        request = Request(url=base_url + path, method=method, headers=headers, data=data)
        return request

    @classmethod
    def execute_request(cls, request):
        try:
            with urlopen(request) as response:
                cls().app_logger.debug(f"Request to {request.full_url} returned {response.status}")
                body = response.read()
                return json.loads(body)

        except HTTPError as exc:
            cls().app_logger.error(f"HTTP error while calling {request.full_url}: {exc}")
            try:
                detail = exc.read().decode()
            except Exception:
                detail = str(exc)
            raise RuntimeError(f"HTTP error: {detail}") from exc

        except URLError as exc:
            cls().app_logger.error(f"URL error while calling {request.full_url}: {exc.reason}")
            raise RuntimeError(f"URL error: {exc.reason}") from exc

        except json.JSONDecodeError as exc:
            cls().app_logger.error(f"Failed to parse JSON response: {exc}!")
            raise RuntimeError("Invalid JSON response.") from exc
