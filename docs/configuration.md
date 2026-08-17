# Configuration & System Properties

The MCT Trading Bot is highly configurable through a combination of environment variables, CLI arguments, and YAML
configuration files.

## System Properties

### Core Configuration

These properties control the fundamental behavior of the bot and its connection to external services.

| Property       | CLI Argument    | Env Variable               | Description                                          | Default          |
|----------------|-----------------|----------------------------|------------------------------------------------------|------------------|
| Environment    | -               | `APP_ENV`                  | Environment mode (`staging`, `production`)           | -                |
| Assets Config  | `--assets-conf` | -                          | Path to the `trading-config.yaml` configuration file | -                |
| Simulated Mode | `--simulated`   | -                          | Enable in-memory order execution                     | `false`          |
| Database Host  | -               | `DATABASE_CONNECTION_HOST` | Host and port for PostgreSQL connection              | `localhost:5432` |

### Backtest Configuration

These properties are specifically for running the bot in backtest mode using historical data.

| Property        | CLI Argument        | Description                             | Default   |
|-----------------|---------------------|-----------------------------------------|-----------|
| Backtest Mode   | `--backtest-mode`   | Enable historical data simulation       | `false`   |
| Backtest Source | `--backtest-source` | Path to historical CSV data directory   | -         |
| Initial Balance | -                   | Starting balance for simulation         | `10000.0` |
| Tick Delay      | -                   | Artificial delay between backtest ticks | `0.0`     |

---

## Asset Configuration (trading-config.yaml)

The `trading-config.yaml` file defines which assets the bot should trade and their specific parameters.

### Consensus Settings

These settings control the thresholds for strategy quorum.

| Field  | Description                                                          | Recommended |
|:-------|:---------------------------------------------------------------------|:------------|
| `buy`  | Consensus factor for BUY actions (True/False ratio). Default: `1.3`  | `1.0 - 2.0` |
| `sell` | Consensus factor for SELL actions (True/False ratio). Default: `0.5` | `0.1 - 1.0` |

```yaml
consensus:
  buy: 1.3
  sell: 0.5
```
  - name: "Bitcoin (Crypto.com)"
    base_ticker_symbol: "BTC"
    quote_ticker_symbol: "USD"
    exchange: "CRYPTO_DOT_COM"
    min_quantity: 0.00001
    quote_decimals: 8
    quantity_decimals: 5
    candles_timeframe: "MIN1"
    schedule: 4
```

For more details on strategy-specific configuration, refer to the [Core Concepts](concepts.md) documentation.

---

## LLM Configuration (`src/configuration/llm.yaml`)

LLM settings live in their own file because they describe **infrastructure**, not trading
behavior. Unlike `trading-config.yaml`, this file is **never modified by the configuration
agent**; changing models or providers is a deployment concern.

### Schedule

| Field      | Description                                       | Default                |
|:-----------|:--------------------------------------------------|:-----------------------|
| `schedule` | How often the LLM analysis scheduler runs.        | `2` (every hour)       |

Values follow the asset schedule enum: `0`=second, `1`=minute, `2`=hour, `3`=day, `4`=week, `5`=month.

### Models

`models` is a list of one or more provider connections. Each entry:

| Field          | Description                                                        |
|:---------------|:-------------------------------------------------------------------|
| `name`         | Logical name used to select the model (e.g. `"default"`).          |
| `provider`     | `ollama`, `deepseek`, `gemini`, or `groq`.                         |
| `model_name`   | Provider-specific model identifier.                                |
| `api_base_url` | Endpoint override; unset uses the provider's default.              |
| `temperature`  | Sampling temperature (default `0.0`).                              |
| `timeout`      | Request timeout in seconds (default unset).                        |
| `keep_alive`   | Keep-alive window for local Ollama models.                         |
| `capabilities` | List of `tools`, `reasoning`, `vision`.                            |
| `roles`        | Reserved for future use; not supported yet.                        |
| `api_key_env`  | Env var holding the API key; unset uses provider-specific env var. |
| `default`      | `true` selects this model when no name is given.                   |

```yaml
schedule: 2
models:
  - name: "default"
    provider: "groq"
    model_name: "openai/gpt-oss-120b"
    temperature: 0.1
    timeout: 120
    capabilities: ["tools", "reasoning"]
    default: true
```

### API keys

Keys are never stored in YAML. Cloud providers resolve their key from an environment
variable: by default `LLM_PROVIDER__<PROVIDER>__API_KEY`, falling back to
`<PROVIDER>_API_KEY` (e.g. `DEEPSEEK_API_KEY`). Set `api_key_env` per model to point at a
custom variable instead.
