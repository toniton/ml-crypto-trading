from unittest import TestCase
from urllib.request import Request

from src.trading.helpers.request_helper import RequestHelper


class TestRequestHelper(TestCase):
    def test_init_http_connection_basic(self):
        base_url = "https://api.example.com/"
        path = "private/create-order"
        data = '{"key":"value"}'.encode("utf-8")

        request = RequestHelper.create_request(base_url, path, method="POST", data=data)

        # Check type
        assert isinstance(request, Request)

        # Check URL
        assert request.full_url == base_url + path

        # Check method
        assert request.method == "POST"

        # Check headers
        # Check User-Agent safely
        assert request.get_header("User-Agent") == "Mozilla/5.0" or request.headers.get("User-agent") == "Mozilla/5.0"

        # Check Content-Type safely (already updated previous block, but ensuring consistency)
        val = request.get_header("Content-Type") or request.headers.get("Content-Type") or request.headers.get(
            "Content-type")
        assert val == "application/json"

        # Check data
        assert request.data == data

    def test_init_http_connection_with_custom_headers(self):
        base_url = "https://api.example.com/"
        path = "private/create-order"
        data = '{"key":"value"}'.encode("utf-8")
        custom_headers = {"Authorization": "Bearer token"}

        request = RequestHelper.create_request(base_url, path, method="POST", data=data, headers=custom_headers)

        # Check merged headers
        # Use safe checking
        assert request.get_header("Content-Type") == "application/json" or request.headers.get(
            "Content-type") == "application/json"
        assert request.get_header("User-Agent") == "Mozilla/5.0" or request.headers.get("User-agent") == "Mozilla/5.0"
        assert request.get_header("Authorization") == "Bearer token" or request.headers.get(
            "Authorization") == "Bearer token"
