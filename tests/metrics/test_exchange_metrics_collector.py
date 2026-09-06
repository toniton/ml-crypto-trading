from src.metrics.collectors.exchange_metrics_collector import ExchangeMetricsCollector
from src.metrics.models.metric_query import MetricQuery
from src.metrics.services.metric_service import MetricService


class TestExchangeMetricsCollector:
    def test_record_request_and_duration(self, db_manager):
        service = MetricService(db_manager)
        collector = ExchangeMetricsCollector(service)

        collector.record_request("BINANCE", "get_market_data")
        collector.record_duration("BINANCE", "get_market_data", 45.0)

        requests = service.query(
            MetricQuery(metric_names=("exchange.requests",), interval_seconds=60)
        )[0]
        durations = service.query(
            MetricQuery(metric_names=("exchange.request.duration",), interval_seconds=60)
        )[0]

        assert [p.value for p in requests.points] == [1.0]
        assert [p.value for p in durations.points] == [45.0]

    def test_record_error(self, db_manager):
        service = MetricService(db_manager)
        collector = ExchangeMetricsCollector(service)

        collector.record_error("COINBASE", "place_order", "HTTPError")

        errors = service.query(
            MetricQuery(metric_names=("exchange.errors",), interval_seconds=60)
        )[0]
        assert [p.value for p in errors.points] == [1.0]

    def test_record_circuit_trip(self, db_manager):
        service = MetricService(db_manager)
        collector = ExchangeMetricsCollector(service)

        collector.record_circuit_trip("BINANCE", "get_candles")

        trips = service.query(
            MetricQuery(metric_names=("circuit_breaker.tripped",), interval_seconds=60)
        )[0]
        assert [p.value for p in trips.points] == [1.0]

    def test_record_websocket_metrics(self, db_manager):
        service = MetricService(db_manager)
        collector = ExchangeMetricsCollector(service)

        collector.record_websocket_message("BINANCE", "PUBLIC")
        collector.record_websocket_error("BINANCE", "MARKET_BTC_USDT", "KeyError")
        collector.record_websocket_reconnect("BINANCE")

        ws_messages = service.query(
            MetricQuery(metric_names=("exchange.websocket.messages",), interval_seconds=60)
        )[0]
        ws_errors = service.query(
            MetricQuery(metric_names=("exchange.websocket.errors",), interval_seconds=60)
        )[0]
        exchange_errors = service.query(
            MetricQuery(metric_names=("exchange.errors",), interval_seconds=60)
        )[0]
        ws_reconnects = service.query(
            MetricQuery(metric_names=("exchange.websocket.reconnects",), interval_seconds=60)
        )[0]

        assert [p.value for p in ws_messages.points] == [1.0]
        assert [p.value for p in ws_errors.points] == [1.0]
        assert [p.value for p in exchange_errors.points] == [1.0]
        assert [p.value for p in ws_reconnects.points] == [1.0]
