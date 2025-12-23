import hashlib
import hmac
import time
from urllib.request import Request

from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import TradeAction
from src.trading.helpers.request_helper import RequestHelper
from src.trading.helpers.trading_helper import TradingHelper
from src.clients.cryptodotcom.cryptodotcom_dto import CryptoDotComRequestAccountBalanceDto, CryptoDotComRequestOrderDto
from src.clients.cryptodotcom.mappers.cryptodotcom_mapper import CryptoDotComMapper
from src.clients.cryptodotcom.utils.helpers import params_to_str


class CryptoDotComRequestFactory:
    @staticmethod
    def build_order_request(
            base_url: str,
            api_key: str,
            secret_key: str,
            uuid: str,
            ticker_symbol: str,
            quantity: str,
            price: str,
            trade_action: TradeAction
    ) -> Request:
        nonce = int(time.time() * 1000)
        request_data = {
            "id": 1,
            "nonce": nonce,
            "method": "private/create-order",
            "api_key": api_key,
            "params": {
                "instrument_name": ticker_symbol,
                "side": trade_action.value.upper(),
                "type": "LIMIT",
                "price": price,
                "quantity": quantity,
                "client_oid": uuid,
                "exec_inst": ["POST_ONLY"],
                "time_in_force": "FILL_OR_KILL"
            }
        }

        payload_str = request_data['method'] \
                      + str(request_data.get('id')) \
                      + request_data['api_key'] \
                      + params_to_str(request_data['params'], 0, 2) \
                      + str(request_data['nonce'])

        request_data['sig'] = hmac.new(
            bytes(str(secret_key), 'utf-8'),
            msg=bytes(payload_str, 'utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()

        request_data_object = CryptoDotComRequestOrderDto(**request_data)

        serialized_json = request_data_object.model_dump_json()

        return RequestHelper.create_request(base_url, "private/create-orderrt", method="POST",
                                            data=serialized_json.encode("utf-8"))

    @staticmethod
    def build_account_balance_request(
            base_url: str,
            api_key: str,
            secret_key: str
    ) -> Request:
        endpoint_path = "private/user-balance"
        nonce = int(time.time() * 1000)
        request_data = {
            "id": 1,
            "nonce": nonce,
            "method": endpoint_path,
            "api_key": api_key,
            "params": {}
        }

        payload_str = request_data['method'] \
                      + str(request_data.get('id')) \
                      + request_data['api_key'] \
                      + params_to_str(request_data['params'], 0, 2) \
                      + str(request_data['nonce'])

        request_data['sig'] = hmac.new(
            bytes(str(secret_key), 'utf-8'),
            msg=bytes(payload_str, 'utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()

        request_data_object = CryptoDotComRequestAccountBalanceDto(**request_data)
        serialized_json = request_data_object.model_dump_json()

        return RequestHelper.create_request(base_url, endpoint_path, method="POST",
                                            data=serialized_json.encode("utf-8"))

    @staticmethod
    def build_account_fees_request(
            base_url: str,
            api_key: str,
            secret_key: str
    ) -> Request:
        endpoint_path = "private/get-fee-rate"
        nonce = int(time.time() * 1000)
        request_data = {
            "id": 1,
            "nonce": nonce,
            "method": endpoint_path,
            "api_key": api_key,
            "params": {}
        }

        payload_str = request_data['method'] \
                      + str(request_data.get('id')) \
                      + request_data['api_key'] \
                      + params_to_str(request_data['params'], 0, 2) \
                      + str(request_data['nonce'])

        request_data['sig'] = hmac.new(
            bytes(str(secret_key), 'utf-8'),
            msg=bytes(payload_str, 'utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()

        request_data_object = CryptoDotComRequestAccountBalanceDto(**request_data)
        serialized_json = request_data_object.model_dump_json()

        return RequestHelper.create_request(base_url, endpoint_path, method="POST",
                                            data=serialized_json.encode("utf-8"))

    @staticmethod
    def build_instrument_fees_request(
            base_url: str,
            api_key: str,
            secret_key: str,
            ticker_symbol: str
    ) -> Request:
        endpoint_path = "private/get-instrument-fee-rate"
        nonce = int(time.time() * 1000)
        instrument_name = TradingHelper.format_ticker_symbol(ticker_symbol, suffix="-PERP")
        request_data = {
            "id": 1,
            "nonce": nonce,
            "method": endpoint_path,
            "api_key": api_key,
            "params": {
                "instrument_name": instrument_name
            }
        }

        payload_str = request_data['method'] \
                      + str(request_data.get('id')) \
                      + request_data['api_key'] \
                      + params_to_str(request_data['params'], 0, 2) \
                      + str(request_data['nonce'])

        request_data['sig'] = hmac.new(
            bytes(str(secret_key), 'utf-8'),
            msg=bytes(payload_str, 'utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()

        request_data_object = CryptoDotComRequestAccountBalanceDto(**request_data)
        serialized_json = request_data_object.model_dump_json()

        return RequestHelper.create_request(base_url, endpoint_path, method="POST",
                                            data=serialized_json.encode("utf-8"))

    @staticmethod
    def build_market_data_request(base_url: str, ticker_symbol: str):
        return RequestHelper.create_request(
            base_url,
            f"public/get-tickers?instrument_name={ticker_symbol}&valuation_type=index_price&count=1"
        )

    @staticmethod
    def build_get_candle_request(base_url: str, ticker_symbol: str, timeframe: Timeframe):
        instrument_name = TradingHelper.format_ticker_symbol(ticker_symbol, suffix="-PERP")
        interval = CryptoDotComMapper.from_timeframe(timeframe)
        return RequestHelper.create_request(
            base_url, f"public/get-candlestick?instrument_name={instrument_name}&timeframe={interval}"
        )
