from src.vcs.application.semantic_merge import SemanticMergeEngine


def test_semantic_merge_clean_disjoint_assets():
    base = {
        "dynamic_quantity": "0.01",
        "assets": [
            {
                "name": "Bitcoin",
                "base_ticker_symbol": "BTC",
                "quote_ticker_symbol": "USD",
                "exchange": "BINANCE",
                "min_quantity": 0.001,
                "quote_decimals": 2,
                "quantity_decimals": 4,
                "candles_timeframe": "1m",
                "schedule": 60,
                "strategies": [{"name": "RSI", "type": "STATIC", "action": "BUY", "enabled": True}],
                "consensus": {"buy": 1.0, "sell": 0.5},
            },
            {
                "name": "Ethereum",
                "base_ticker_symbol": "ETH",
                "quote_ticker_symbol": "USD",
                "exchange": "BINANCE",
                "min_quantity": 0.01,
                "quote_decimals": 2,
                "quantity_decimals": 3,
                "candles_timeframe": "1m",
                "schedule": 60,
                "strategies": [{"name": "MACD", "type": "STATIC", "action": "SELL", "enabled": True}],
                "consensus": {"buy": 0.8, "sell": 0.6},
            },
        ],
    }

    # Ours (main) changed ETH consensus
    ours = {
        "dynamic_quantity": "0.01",
        "assets": [
            base["assets"][0],
            {
                **base["assets"][1],
                "consensus": {"buy": 0.9, "sell": 0.6},  # Changed on main
            },
        ],
    }

    # Theirs (backtest) changed BTC consensus
    theirs = {
        "dynamic_quantity": "0.01",
        "assets": [
            {
                **base["assets"][0],
                "consensus": {"buy": 0.75, "sell": 0.5},  # Changed on backtest
            },
            base["assets"][1],
        ],
    }

    merged, conflicts = SemanticMergeEngine.merge(base, ours, theirs)

    assert len(conflicts) == 0
    btc_merged = next(a for a in merged["assets"] if a["base_ticker_symbol"] == "BTC")
    eth_merged = next(a for a in merged["assets"] if a["base_ticker_symbol"] == "ETH")

    assert btc_merged["consensus"]["buy"] == 0.75  # Taken from backtest
    assert eth_merged["consensus"]["buy"] == 0.9   # Preserved from main


def test_semantic_merge_detects_conflict_on_same_field():
    base = {
        "dynamic_quantity": "0.01",
        "assets": [
            {
                "name": "Bitcoin",
                "base_ticker_symbol": "BTC",
                "quote_ticker_symbol": "USD",
                "exchange": "BINANCE",
                "min_quantity": 0.001,
                "quote_decimals": 2,
                "quantity_decimals": 4,
                "candles_timeframe": "1m",
                "schedule": 60,
                "strategies": [],
                "consensus": {"buy": 1.0, "sell": 0.5},
            }
        ],
    }

    # Both modified BTC consensus buy threshold to different values
    ours = {
        "dynamic_quantity": "0.01",
        "assets": [{**base["assets"][0], "consensus": {"buy": 0.65, "sell": 0.5}}],
    }
    theirs = {
        "dynamic_quantity": "0.01",
        "assets": [{**base["assets"][0], "consensus": {"buy": 0.85, "sell": 0.5}}],
    }

    merged, conflicts = SemanticMergeEngine.merge(base, ours, theirs)

    assert len(conflicts) == 1
    assert conflicts[0].path == "assets.BTC_USD.consensus.buy"
    assert conflicts[0].ours_value == 0.65
    assert conflicts[0].theirs_value == 0.85
