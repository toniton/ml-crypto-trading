from api.interfaces.timeframe import Timeframe


class CryptoDotComTimeframe:
    MAP = {
        Timeframe.MIN1: "1m",
        Timeframe.MIN5: "5m",
        Timeframe.MIN15: "15m",
        Timeframe.MIN30: "30m",
        Timeframe.HOUR1: "1h",
        Timeframe.HOUR2: "2h",
        Timeframe.HOUR4: "4h",
        Timeframe.HOUR12: "12h",
        Timeframe.DAY1: "1D",
        Timeframe.DAY7: "7D",
        Timeframe.MON1: "1M",
    }
