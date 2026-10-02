from decimal import Decimal
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from src.trading.regimes.market_regime import MarketRegime
from src.trading.regimes.market_regime_detector import MarketRegimeDetector


def _make_candle(high: float, low: float, close: float, start_time: int = 0) -> Candle:
    return Candle(
        start_time=float(start_time),
        open=Decimal(str((high + low) / 2)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
    )


def test_detector_returns_unknown_when_insufficient_candles():
    detector = MarketRegimeDetector()
    market_data = MarketData(
        volume=Decimal("100"),
        high_price=Decimal("105"),
        low_price=Decimal("95"),
        close_price=Decimal("100"),
        timestamp=1000.0,
    )
    candles = [_make_candle(105, 95, 100)]
    metrics = detector.detect(candles, market_data)

    assert metrics.regime == MarketRegime.UNKNOWN


def test_detector_returns_illiquid_when_zero_volume():
    detector = MarketRegimeDetector()
    market_data = MarketData(
        volume=Decimal("0"),
        high_price=Decimal("105"),
        low_price=Decimal("95"),
        close_price=Decimal("100"),
        timestamp=1000.0,
    )
    candles = [
        _make_candle(105, 95, 100, start_time=i)
        for i in range(10)
    ]
    metrics = detector.detect(candles, market_data)

    assert metrics.regime == MarketRegime.ILLIQUID
    assert metrics.liquidity == 0.0


def test_detector_returns_high_volatility():
    detector = MarketRegimeDetector(high_volatility_threshold=0.03)
    market_data = MarketData(
        volume=Decimal("100"),
        high_price=Decimal("110"),
        low_price=Decimal("90"),
        close_price=Decimal("100"),
        timestamp=1000.0,
    )
    candles = [
        _make_candle(110, 90, 100, start_time=i)
        for i in range(10)
    ]
    metrics = detector.detect(candles, market_data)

    assert metrics.regime == MarketRegime.HIGH_VOLATILITY
    assert metrics.volatility >= 0.03


def test_detector_returns_trending_up():
    detector = MarketRegimeDetector(
        high_volatility_threshold=0.10,
        low_volatility_threshold=0.001,
        trend_threshold=0.005,
    )
    prices = [100.0 + i * 2.0 for i in range(25)]
    candles = [
        _make_candle(p + 0.5, p - 0.5, p, start_time=i)
        for i, p in enumerate(prices)
    ]
    market_data = MarketData(
        volume=Decimal("100"),
        high_price=Decimal(str(prices[-1] + 0.5)),
        low_price=Decimal(str(prices[-1] - 0.5)),
        close_price=Decimal(str(prices[-1])),
        timestamp=1000.0,
    )
    metrics = detector.detect(candles, market_data)

    assert metrics.regime == MarketRegime.TRENDING_UP
    assert metrics.trend_strength > 0.005


def test_detector_returns_trending_down():
    detector = MarketRegimeDetector(
        high_volatility_threshold=0.10,
        low_volatility_threshold=0.001,
        trend_threshold=0.005,
    )
    prices = [200.0 - i * 2.0 for i in range(25)]
    candles = [
        _make_candle(p + 0.5, p - 0.5, p, start_time=i)
        for i, p in enumerate(prices)
    ]
    market_data = MarketData(
        volume=Decimal("100"),
        high_price=Decimal(str(prices[-1] + 0.5)),
        low_price=Decimal(str(prices[-1] - 0.5)),
        close_price=Decimal(str(prices[-1])),
        timestamp=1000.0,
    )
    metrics = detector.detect(candles, market_data)

    assert metrics.regime == MarketRegime.TRENDING_DOWN
    assert metrics.trend_strength < -0.005


def test_detector_returns_low_volatility():
    detector = MarketRegimeDetector(
        high_volatility_threshold=0.05,
        low_volatility_threshold=0.005,
        trend_threshold=0.05,
    )
    candles = [
        _make_candle(100.01, 99.99, 100.0, start_time=i)
        for i in range(25)
    ]
    market_data = MarketData(
        volume=Decimal("100"),
        high_price=Decimal("100.01"),
        low_price=Decimal("99.99"),
        close_price=Decimal("100.0"),
        timestamp=1000.0,
    )
    metrics = detector.detect(candles, market_data)

    assert metrics.regime == MarketRegime.LOW_VOLATILITY
    assert metrics.volatility <= 0.005


def test_detector_spread_with_order_book():
    detector = MarketRegimeDetector()
    market_data_with_book = MarketData(
        volume=Decimal("100"),
        high_price=Decimal("105"),
        low_price=Decimal("95"),
        close_price=Decimal("100"),
        timestamp=1000.0,
        bid_price=Decimal("99.90"),
        ask_price=Decimal("100.10"),
    )
    spread = detector.calculate_spread(market_data_with_book, 100.0)
    assert abs(spread - 0.002) < 1e-6

    market_data_without_book = MarketData(
        volume=Decimal("100"),
        high_price=Decimal("101"),
        low_price=Decimal("99"),
        close_price=Decimal("100"),
        timestamp=1000.0,
    )
    assert detector.calculate_spread(market_data_without_book, 100.0) == 0.0


def test_detector_classify_with_spread():
    detector = MarketRegimeDetector(illiquid_spread_threshold=0.05)

    assert detector.classify(
        trend_strength=0.0,
        volatility=0.01,
        liquidity=100.0,
        spread=0.06,
    ) == MarketRegime.ILLIQUID

    assert detector.classify(
        trend_strength=0.01,
        volatility=0.01,
        liquidity=100.0,
        spread=0.01,
    ) == MarketRegime.TRENDING_UP
