import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.logging.application_logging_mixin import ApplicationLoggingMixin


class ExchangeRequestError(RuntimeError):
    def __init__(
            self,
            message: str,
            http_status: int = None,
            response_body: Any = None,
            url: str = None,
            method: str = "GET",
    ):
        super().__init__(message)
        self.http_status = http_status
        self.response_body = response_body
        self.url = url
        self.method = method


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
            except UnicodeDecodeError:
                detail = str(exc)
            parsed_body = None
            try:
                parsed_body = json.loads(detail)
            except Exception:
                parsed_body = detail
            raise ExchangeRequestError(
                f"HTTP error: {detail}",
                http_status=exc.code,
                response_body=parsed_body,
                url=request.full_url,
                method=request.get_method(),
            ) from exc

        except URLError as exc:
            cls().app_logger.error(f"URL error while calling {request.full_url}: {exc.reason}")
            raise RuntimeError(f"URL error: {exc.reason}") from exc

        except json.JSONDecodeError as exc:
            cls().app_logger.error(f"Failed to parse JSON response: {exc}!")
            raise RuntimeError("Invalid JSON response.") from exc
