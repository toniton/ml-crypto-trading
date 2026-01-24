# Configuration & System Properties

The MCT Trading Bot is highly configurable through a combination of environment variables, CLI arguments, and YAML
configuration files.

## System Properties

### Core Configuration

These properties control the fundamental behavior of the bot and its connection to external services.

| Property       | CLI Argument    | Env Variable               | Description                                  | Default          |
|----------------|-----------------|----------------------------|----------------------------------------------|------------------|
| Environment    | -               | `APP_ENV`                  | Environment mode (`staging`, `production`)   | -                |
| Assets Config  | `--assets-conf` | -                          | Path to the `assets.yaml` configuration file | -                |
| Simulated Mode | `--simulated`   | -                          | Enable in-memory order execution             | `false`          |
| Database Host  | -               | `DATABASE_CONNECTION_HOST` | Host and port for PostgreSQL connection      | `localhost:5432` |

### Backtest Configuration

These properties are specifically for running the bot in backtest mode using historical data.

| Property        | CLI Argument        | Description                             | Default   |
|-----------------|---------------------|-----------------------------------------|-----------|
| Backtest Mode   | `--backtest-mode`   | Enable historical data simulation       | `false`   |
| Backtest Source | `--backtest-source` | Path to historical CSV data directory   | -         |
| Initial Balance | -                   | Starting balance for simulation         | `10000.0` |
| Tick Delay      | -                   | Artificial delay between backtest ticks | `0.0`     |

---

## Asset Configuration (assets.yaml)

The `assets.yaml` file defines which assets the bot should trade and their specific parameters.

```yaml
assets:
  - name: "Bitcoin (Crypto.com)"
    base_ticker_symbol: "BTC"
    quote_ticker_symbol: "USD"
    exchange: "CRYPTO_DOT_COM"
    min_quantity: 0.00001
    decimal_places: 8
    candles_timeframe: "MIN1"
    schedule: 4
```

For more details on strategy-specific configuration, refer to the [Core Concepts](concepts.md) documentation.
