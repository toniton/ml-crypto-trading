# Configuration & System Properties

The MCT Trading Bot is highly configurable through a combination of environment variables, CLI arguments, and YAML
configuration files.

## System Properties

### Core Configuration

These properties control the fundamental behavior of the bot, runtime modes, and external connectivity.

| Property       | CLI Argument    | Env Variable               | Description                                          | Default          |
|----------------|-----------------|----------------------------|------------------------------------------------------|------------------|
| Environment    | -               | `APP_ENV`                  | Environment mode (`staging`, `production`)           | -                |
| Assets Config  | `--assets-conf` | -                          | Path to the `trading-config.yaml` configuration file | Required         |
| Simulated Mode | `--simulated`   | -                          | Enable in-memory order execution (paper trading)     | `false`          |
| Headless Mode  | `--headless`    | -                          | Run without interactive/UI processes                 | `false`          |
| Database Host  | -               | `DATABASE_CONNECTION_HOST` | Host and port for PostgreSQL connection              | `localhost:5432` |
| Postgres User  | -               | `POSTGRES_USER`            | Database username                                    | `postgres`       |
| Postgres DB    | -               | `POSTGRES_DATABASE`        | Database name                                        | `trading_bot`    |
| Log Directory  | -               | `LOG_DIR`                  | Destination folder for log files                     | `.`              |
| Log Level      | -               | `LOG_LEVEL`                | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)  | Env-dependent    |

### Exchange & CCXT Credentials

Credentials can be supplied via environment variables with nested delimiters (`__`):

```env
# Crypto.com Native
CRYPTO_DOT_COM__API_KEY=your_api_key
CRYPTO_DOT_COM__SECRET_KEY=your_secret_key

# CCXT Providers
CCXT_PROVIDERS__BINANCE__API_KEY=your_binance_key
CCXT_PROVIDERS__BINANCE__SECRET_KEY=your_binance_secret
CCXT_PROVIDERS__KRAKEN__API_KEY=your_kraken_key
CCXT_PROVIDERS__KRAKEN__SECRET_KEY=your_kraken_secret
CCXT_PROVIDERS__COINBASE__API_KEY=your_coinbase_key
CCXT_PROVIDERS__COINBASE__SECRET_KEY=your_coinbase_secret
```

### Backtest Configuration

These properties control historical simulation and market friction modeling:

| Property        | CLI Argument            | Description                                      | Default   |
|-----------------|-------------------------|--------------------------------------------------|-----------|
| Backtest Mode   | `--backtest-mode`       | Enable historical data simulation                | `false`   |
| Backtest Source | `--backtest-source`     | Path to historical CSV / recorded audit data     | -         |
| Initial Balance | -                       | Starting quote currency balance                  | `10000.0` |
| Tick Delay      | -                       | Artificial delay between backtest ticks (sec)    | `0.0`     |
| Latency         | `--backtest-latency-ms` | Simulated execution latency in milliseconds      | `500.0`   |
| Slippage        | `--backtest-slippage-ticks` | Simulated slippage in exchange tick units    | `2`       |
| Fee Rate        | `--backtest-fee-rate`   | Fee rate as decimal (e.g. `0.001` = 0.1%)        | `0.001`   |

---

## Asset Configuration (trading-config.yaml)

The `trading-config.yaml` file defines which assets the bot should trade and their specific parameters.

### Consensus Settings

Each asset carries its **own** consensus thresholds that control how many strategy votes are
required before that asset trades. Consensus is evaluated separately per asset (and per
action), so assets never share votes or thresholds.

`consensus` is a **required** per-asset block — there is no global default. An asset that
omits `consensus` has no threshold and will never reach quorum.

Quorum is satisfied when:

$$\text{true\_count} \ge \text{factor} \times (\text{total} - \text{true\_count})$$

| Field  | Description                                                          | Recommended |
|:-------|:---------------------------------------------------------------------|:------------|
| `buy`  | Consensus factor for BUY actions (True/False ratio). Required, no default. | `0.5 - 2.0` |
| `sell` | Consensus factor for SELL actions (True/False ratio). Required, no default. | `0.5 - 2.0` |

#### Common Consensus Configurations

##### 1. Single Strategy (1-of-1 Consensus)
Add 1 strategy and configure `1.0` consensus. The strategy executes whenever its condition evaluates to `True`.

```yaml
assets:
  - name: "Bitcoin (Single Strategy)"
    base_ticker_symbol: "BTC"
    quote_ticker_symbol: "USD"
    # ...
    strategies:
      - name: "RsiOversoldBuy"
        type: "DYNAMIC"
        action: "BUY"
        expression: "rsi(14) < 25"
      - name: "RsiOverboughtSell"
        type: "DYNAMIC"
        action: "SELL"
        expression: "rsi(14) > 75"
    consensus:
      buy: 1.0
      sell: 1.0
```

##### 2. Multi Strategy (1-of-2 Consensus — Trade on Each Strategy)
Add 2 strategies and configure `0.5` consensus (or any factor $\le 1.0$). Quorum is reached when **any** strategy signals `True` ($1 \ge 0.5 \times 1$).

```yaml
assets:
  - name: "Ethereum (Trade On Any Strategy)"
    base_ticker_symbol: "ETH"
    quote_ticker_symbol: "USD"
    # ...
    strategies:
      - name: "RsiOversoldBuy"
        type: "DYNAMIC"
        action: "BUY"
        expression: "rsi(14) < 25"
      - name: "BreakoutBuy"
        type: "DYNAMIC"
        action: "BUY"
        expression: "close > sma(50) and volume > 50"
      - name: "RsiOverboughtSell"
        type: "DYNAMIC"
        action: "SELL"
    consensus:
      buy: 0.5
      sell: 0.5
```

##### 3. Multi Strategy (2-of-2 Consensus — Trade on Quorum of Strategies)
Add 2 strategies and configure `1.3` consensus (or any factor $> 1.0$). Quorum requires **both** strategies to agree ($2 \ge 1.3 \times 0$). A single vote will fail quorum ($1 < 1.3 \times 1$).

```yaml
assets:
  - name: "Solana (Strict Quorum Agreement)"
    base_ticker_symbol: "SOL"
    quote_ticker_symbol: "USD"
    # ...
    strategies:
      - name: "HammerAccumulationStrategy"
        type: "STATIC"
        class_name: "HammerAccumulationStrategy"
        action: "BUY"
      - name: "RsiOversoldBuy"
        type: "DYNAMIC"
        action: "BUY"
        expression: "rsi(14) < 30"
      - name: "RsiOverboughtSell"
        type: "DYNAMIC"
        action: "SELL"
    consensus:
      buy: 1.3
      sell: 0.5
```

### Strategies

Strategies are defined **per asset** and vote for a single direction. Each asset declares
its strategies explicitly in its `strategies` list — there are no global strategies and no
implicit inheritance. A strategy entry distinguishes how it is implemented from the
direction it votes for:

| Field        | Description                                                            |
|:-------------|:-----------------------------------------------------------------------|
| `name`       | Identifier of the strategy (must be unique per asset). For `STATIC` entries it defaults to `class_name`. |
| `type`       | How the strategy is implemented: `STATIC` (built-in Python class) or `DYNAMIC` (evaluated expression). |
| `class_name` | For `STATIC` strategies: the built-in Python class to instantiate. `DYNAMIC` entries must not define it. |
| `action`     | Direction the strategy votes for: `BUY` or `SELL`.                     |
| `expression` | For `DYNAMIC` strategies: evaluated against the market/position/indicator context. `True` means the strategy votes in its direction. |
| `enabled`    | Whether the strategy participates in the consensus calculation. Default: `true`. |

An entry can be either:

- **Inline definition** — the strategy is declared fully on the asset. A `DYNAMIC` entry
  provides the `expression` (validated at config load and evaluated deterministically with
  the same `ExpressionParser` used for `dynamic_quantity` — no arbitrary Python is
  executed); a `STATIC` entry just names the built-in class via `class_name`. Facts not
  given inline (an expression template or its `action`) are completed from `strategies.yaml`.
- **Predefined reference** — `name` + `type`, plus whatever it needs: built-in `STATIC`
  classes need no `action` (it comes from the class), `DYNAMIC` entries take the
  `expression`/`action` from `strategies.yaml`. When either axis is ambiguous at load time,
  configuration fails with a clear error.

`action` for `STATIC` strategies cannot disagree with the built-in class vote; `DYNAMIC`
strategies without an `expression` must have a matching registry template.

Available variables in the expression context: `close`, `high`, `low`, `volume`, `range`,
`range_pct`, `position_qty`, `avg_entry`, `pnl`, `exit_qty`, `avg_exit_price`,
`realized_pnl`. Available functions: `min`, `max`, `avg`, `sma(n)`, `ema(n)`, `rsi(n)`.

```yaml
assets:
  - name: "Bitcoin (Crypto.com)"
    base_ticker_symbol: "BTC"
    quote_ticker_symbol: "USD"
    # ...
    strategies:
      - name: "HammerAccumulationStrategy"  # built-in static strategy
        type: "STATIC"
        class_name: "HammerAccumulationStrategy"
      - name: "RsiOversoldBuy"              # inline DYNAMIC definition (overrides the registry for BTC)
        type: "DYNAMIC"
        action: "BUY"
        expression: "rsi(14) < 20"
      - name: "RsiOverboughtSell"           # reference: expression/action taken from strategies.yaml
        type: "DYNAMIC"
        action: "SELL"
      - name: "BreakoutBuy"                 # asset-specific strategy
        type: "DYNAMIC"
        action: "BUY"
        expression: "close > sma(50) and range_pct > 0.03"
  - name: "Doge (Crypto.com)"
    base_ticker_symbol: "DOGE"
    quote_ticker_symbol: "USD"
    # ...
    strategies:
      - name: "RsiOversoldBuy"              # reference
        type: "DYNAMIC"
      - name: "TrendFollowingBuy"
        type: "DYNAMIC"
        enabled: false                      # listed but disabled for DOGE
```

Because strategies are explicit per asset, an asset that declares **no** strategies has no
voting strategies and will not trade (an empty consensus bucket yields no quorum). The
`StrategyResolver` is pure configuration logic: given an asset and the registry it always
produces the same effective strategy list and never evaluates expressions or reads market
data. Evaluation happens later in the `ExpressionStrategy`; voting stays with the
`ConsensusManager`.

### Predefined strategies (`strategies.yaml`)

Reusable strategy definitions live in a separate registry file, `strategies.yaml`, loaded by
`StrategiesConfig` from its default location. Assets reference registry
entries by name.
Registry entries describe either **built-in static strategies** (Python classes such as
`HammerAccumulationStrategy`, declared with `type: STATIC` + `class_name`) or **expression
templates** (`type: DYNAMIC` + `action` + `expression`). The shipped default file declares
the built-in statics.

```yaml
strategies:
  - name: "HammerAccumulationStrategy"   # built-in static strategy
    type: "STATIC"
    class_name: "HammerAccumulationStrategy"
    action: "BUY"
  - name: "ShootingStarSellStrategy"     # built-in static strategy
    type: "STATIC"
    class_name: "ShootingStarSellStrategy"
    action: "SELL"
  - name: "RsiOversoldBuy"               # reusable expression template
    type: "DYNAMIC"
    action: "BUY"
    expression: "rsi(14) < 25"
  - name: "RsiOverboughtSell"
    type: "DYNAMIC"
    action: "SELL"
    expression: "rsi(14) > 78 and position_qty > 0"
```

Resolution follows the entry's declared `type`:

- `STATIC` — the built-in strategy class named by `class_name` is found and instantiated;
  the asset's `action`, if given, must match the class's vote.
- `DYNAMIC` — an inline `expression` wins; otherwise the `strategies.yaml` template for that
  name supplies the `expression` (and `action` if the asset omitted it). Missing
  expression/action on both sides fails configuration with a clear error.

The registry is not modified by the configuration agent; assets opt in explicitly.

### Consensus debug logging

Every consensus decision logs one INFO line naming each registered strategy and its vote,
e.g.:

```
Consensus [BTC_USD BUY]: HammerAccumulationStrategy=True, RsiOversoldBuy=False -> Quorum=False (1/2)
```

`true` votes are counted against the consensus factor (`buy`/`sell`); the trailing `(True/Total)`
summarizes the raw votes for quick debugging.

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

---

## REST API & WebSocket Endpoints

When running the server (`--server=true`), FastAPI provides the following endpoints:

| Method | Endpoint | Description |
|:-------|:---------|:------------|
| `POST` | `/api/v1/chat` | Server-Sent Events (SSE) chat stream with the LangGraph AI Agent. |
| `GET`  | `/api/v1/sessions` | List active agent conversation sessions. |
| `GET`  | `/api/v1/sessions/{session_id}` | Retrieve message history for a specific conversation session. |
| `POST` | `/api/v1/proposals/{message_id}/decision` | Approve or reject a pending configuration change proposal. |
| `GET`  | `/api/v1/config` | Retrieve current active bot configuration. |
| `GET`  | `/api/v1/config/options` | Retrieve supported exchanges, timeframes, and strategies. |
| `POST` | `/api/v1/config` | Direct commit of configuration to VCS. |
| `GET`  | `/api/v1/vcs/log` | Query configuration version control commit history. |
| `GET`  | `/api/v1/vcs/checkout/{commit_hash}` | Inspect or restore configuration at a specific commit hash. |
| `GET`  | `/api/v1/heatmap/orders/{year}/{month}` | Daily trade counts and volume heatmap. |
| `GET`  | `/api/v1/orders/{year}/{month}/{day}` | Detailed trade records for a specific day. |
| `GET`  | `/api/v1/orders/week/{year}/{month}/{day}` | Weekly aggregated trade summary. |
| `GET`  | `/api/v1/orders/latency/{year}/{month}` | Execution latency distribution and percentiles. |
| `GET`  | `/api/v1/runtime` | Live CPU, memory, and process health metrics. |
| `GET`  | `/api/v1/orders/lifecycle` | Order lifecycle telemetry and fill statistics. |
| `WS`   | `/api/v1/logs/ws` | Real-time WebSocket stream for application and trading log events. |
