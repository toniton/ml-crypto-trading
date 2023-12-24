import decimal
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

from entities.exchange_provider import ExchangeProvidersEnum
from entities.trade_action import TradeAction
from trading.orders.providers.cryptodotcom_dto import CryptoDotComRequestDto, CryptoDotComResponseOrderCreatedDto
from trading.orders.providers.exchange_provider import ExchangeProvider
from trading.orders.utils.helpers import params_to_str


class CryptoDotComProvider(ExchangeProvider):

    def __init__(self, _base_url: str, _api_key: str, _secret_key: str):
        self.base_url = _base_url
        self.api_key = _api_key
        self.secret_key = _secret_key

    def get_provider_name(self):
        return ExchangeProvidersEnum.CRYPTO_DOT_COM.name

    def init_http_connection(self, path: str, method: str = "GET", data: Any = None, headers: dict = None) -> Request:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            **(headers or {})
        }
        request = Request(url=self.base_url + path, method=method, headers=headers, data=data)
        return request

    def get_market_price(self, ticker_symbol: str) -> decimal:
        request = self.init_http_connection(
            f"public/get-ticker?instrument_name={ticker_symbol}&valuation_type=index_price&count=1"
        )

        with urlopen(request) as response:
            body = response.read()
            data = json.loads(body)

        return data["result"]["data"][0]["a"]

    def _build_order_request(
            self,
            uuid: UUID,
            ticker_symbol: str,
            quantity: int,
            price: str,
            trade_action: TradeAction
    ) -> CryptoDotComRequestDto:
        nonce = int(time.time() * 1000)
        request_data = {
            "id": 1,
            "nonce": nonce,
            "method": "private/create-order",
            "api_key": self.api_key,
            "params": {
                "instrument_name": ticker_symbol,
                "side": str(trade_action.value.upper()),
                "type": "LIMIT",
                "price": float(price),
                "quantity": int(quantity),
                "client_oid": str(uuid),
                "exec_inst": "POST_ONLY",
                "time_in_force": "FILL_OR_KILL"
            }
        }

        payload_str = request_data['method'] \
            + str(request_data.get('id')) \
            + request_data['api_key'] \
            + params_to_str(request_data['params'], 0, 2) \
            + str(request_data['nonce'])

        request_data['sig'] = hmac.new(
            bytes(str(self.secret_key), 'utf-8'),
            msg=bytes(payload_str, 'utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()
        return CryptoDotComRequestDto(**request_data)

    def place_order(
            self,
            uuid: UUID,
            ticker_symbol: str,
            quantity: int,
            price: str,
            trade_action: TradeAction
    ) -> CryptoDotComResponseOrderCreatedDto:
        request_data = self._build_order_request(uuid, ticker_symbol, quantity, price, trade_action)
        serialized_json = request_data.model_dump_json()

        request = self.init_http_connection(
            "private/create-order",
            method="POST",
            data=serialized_json.encode("utf-8")
        )

        try:
            with urlopen(request) as response:
                body = response.read()
                data = json.loads(body)
            return CryptoDotComResponseOrderCreatedDto(**data["result"])
        except HTTPError as exc:
            print(exc.read().decode())
        except URLError as exc:
            print(exc.reason)
