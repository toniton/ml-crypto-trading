# MCT Trading Bot

[![CI](https://github.com/toniton/ml-crypto-trading/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/toniton/ml-crypto-trading/actions/workflows/ci.yml)
[![linting: pylint](https://img.shields.io/badge/linting-pylint-yellowgreen)](https://github.com/pylint-dev/pylint)
[![codecov](https://codecov.io/github/toniton/ml-crypto-trading/graph/badge.svg?token=N0VBWT87L7)](https://codecov.io/github/toniton/ml-crypto-trading)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Docker pull](https://img.shields.io/docker/pulls/toniton/ml-crypto-trading)](https://hub.docker.com/r/toniton/ml-crypto-trading)
[![Discord chat](https://img.shields.io/discord/1465111294880518248?logo=discord&style=flat)](https://discord.gg/vZh8w3Sz)

MCT (stands for ML-Crypto-Trading) is a high-performance trading engine that features a **Dynamic Expression Engine**
allowing users to define position sizing and risk management logic using familiar, spreadsheet-like functions.

> [!TIP]
> **Financial Logic Without the Code.**
> If you can write an Excel-style formula, you can define trading logic in MCT. The engine provides access to real-time
> market data, balances, and technical indicators (RSI, EMA, SMA) directly in your configuration.

> Caveat Utilitor! For educational and research purposes only.

---

## Community

Join our Discord community to discuss strategies, report issues, and collaborate with other traders:

[![Discord Banner](https://img.shields.io/discord/1465111294880518248?label=Discord&logo=discord&style=for-the-badge)](https://discord.gg/vZh8w3Sz)


---

## Core Features

- 🧠 **AI Agent & LangGraph Workflows**: Interactive multi-agent assistant with specialized subgraphs for configuration tuning, on-demand backtesting, trading performance analytics, and a proactive Trading Oracle.
- 📐 **Dynamic Expression Engine**: Define position sizing and custom strategy logic using spreadsheet formulas (`rsi`, `sma`, `ema`, `balance`, `equity`, `pnl`, etc.).
- 🤝 **BFT Consensus Engine**: Flexible multi-strategy quorum voting supporting 1-of-1 single strategy, 1-of-2 independent triggers, and 2-of-2 strict consensus.
- 📊 **High-Fidelity Backtesting**: Multi-asset independent clock simulation with realistic execution frictions (slippage, latency, fees), drift detection, and tick replay.
- 🌐 **REST API & Real-Time WebSockets**: FastAPI server providing order analytics, monthly heatmaps, latency metrics, configuration proposals, and live log streaming (`/api/v1/logs/ws`).
- 📈 **Runtime Observability & Metrics**: Built-in collectors for CPU/memory usage, WebSocket health, order lifecycle timings, and exchange telemetry.
- 📜 **Configuration Version Control (VCS)**: Git-like history tracking, audit trail, and rollback for runtime configuration changes.

---

## Quick Start

The easiest way to run the bot is using **Docker** or standard Python.

### Prerequisites

- **Docker & Docker Compose** (or Python 3.11+)
- **PostgreSQL**: A running instance (local or remote) to store trading history.

### 1. Configuration

Create your asset configuration and environment variables.

**trading-config.yaml**
```yaml
assets:
  - name: "Bitcoin (Crypto.com)"
    base_ticker_symbol: "BTC"
    quote_ticker_symbol: "USD"
    exchange: "CRYPTO_DOT_COM"
    min_quantity: 0.00005
    quote_decimals: 2
    quantity_decimals: 5
    candles_timeframe: "MIN1"
    schedule: 1
    strategies:
      - name: "HammerAccumulationStrategy"
        type: "STATIC"
        class_name: "HammerAccumulationStrategy"
        action: "BUY"
      - name: "RsiOversoldBuy"
        type: "DYNAMIC"
        action: "BUY"
        expression: "rsi(14) < 20"
      - name: "RsiOverboughtSell"
        type: "DYNAMIC"
        action: "SELL"
    consensus:
      buy: 1.3
      sell: 0.5
dynamic_quantity: "max(min_qty, (balance * 0.02) / close)"
```

### Consensus Configurations

MCT uses a Byzantine Fault Tolerant (BFT) voting system where trade actions execute when consensus quorum is satisfied:
$$\text{true\_count} \ge \text{factor} \times (\text{total} - \text{true\_count})$$

You can configure consensus per asset depending on your trading strategy:

- **Single Strategy (1-of-1 Consensus)**:
  Configure 1 strategy with `consensus.buy: 1.0` and `consensus.sell: 1.0`. The trade triggers whenever that single strategy votes `True`.
  ```yaml
  strategies:
    - name: "RsiOversoldBuy"
      type: "DYNAMIC"
      action: "BUY"
      expression: "rsi(14) < 30"
  consensus:
    buy: 1.0
    sell: 1.0
  ```

- **Multi Strategy (1-of-2 Consensus — Trade on Each Strategy)**:
  Configure 2 strategies with `consensus.buy: 0.5` (or any factor $\le 1.0$). If **either** strategy signals a trade (1 of 2), quorum is met ($1 \ge 0.5 \times 1$).
  ```yaml
  strategies:
    - name: "RsiOversoldBuy"
      type: "DYNAMIC"
      action: "BUY"
      expression: "rsi(14) < 30"
    - name: "BreakoutBuy"
      type: "DYNAMIC"
      action: "BUY"
      expression: "close > sma(50) and volume > 100"
  consensus:
    buy: 0.5
    sell: 0.5
  ```

- **Multi Strategy (2-of-2 Consensus — Trade on Quorum / Agreement)**:
  Configure 2 strategies with `consensus.buy: 1.3` (or any factor $> 1.0$). A trade triggers **only when both** strategies agree ($2 \ge 1.3 \times 0$, but $1 < 1.3 \times 1$).
  ```yaml
  strategies:
    - name: "RsiOversoldBuy"
      type: "DYNAMIC"
      action: "BUY"
      expression: "rsi(14) < 30"
    - name: "HammerAccumulationStrategy"
      type: "STATIC"
      class_name: "HammerAccumulationStrategy"
      action: "BUY"
  consensus:
    buy: 1.3
    sell: 0.5
  ```

**.env**

```env
APP_ENV=production
CRYPTO_DOT_COM__API_KEY=your_api_key
CRYPTO_DOT_COM__SECRET_KEY=your_secret_key
DATABASE_CONNECTION_HOST=localhost:5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_DATABASE=trading_bot
```

### 2. Run Modes

#### 📊 Backtesting (Historical Data & Replay)

Test your strategies against historical CSV or recorded audit data with realistic execution frictions (slippage, latency, fees):
```bash
docker run -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/trading-config.yaml \
  --backtest-mode=true \
  --backtest-source=/workspace/history/ \
  --backtest-latency-ms=500.0 \
  --backtest-slippage-ticks=2 \
  --backtest-fee-rate=0.001
```

#### 🧪 Simulated Trading (Paper Trading)

Run the bot with live market streams while intercepting and executing orders in memory:
```bash
docker run --env-file .env -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/trading-config.yaml \
  --simulated=true
```

#### 🚀 Live Trading (Real Exchange)

Execute live orders on the configured exchange:
```bash
docker run --env-file .env -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/trading-config.yaml
```

#### 🌐 REST API & AI Agent Server

Start the integrated FastAPI and AI Agent server for interactive chat, log streaming, and metric APIs:
```bash
docker run --env-file .env -p 8000:8000 -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/trading-config.yaml \
  --server=true \
  --api-port=8000
```

---

## Documentation

For comprehensive information, please explore the documentation in the `docs/` directory:

- [Introduction & Features](docs/introduction.md) — System motivation and comprehensive feature breakdown.
- [Core Concepts](docs/concepts.md) — Consensus model, Dynamic expressions, AI Agent architecture, and Backtesting.
- [Configuration & System Properties](docs/configuration.md) — CLI flags, environment variables, and YAML schemas.
- [Architecture & Diagrams](docs/architecture.md) — Manager layer, Agent graphs, API server, and system flow.
- [Logging Architecture](docs/logging.md) — Application, trading, audit replay, and WebSocket log streaming.
- [Community & Contributing](docs/community.md) — Contributing guidelines and Discord community.

---

## License

This source code is available on GitHub under
the [GNU Lesser General Public License v3.0](https://www.gnu.org/licenses/lgpl-3.0.en.html).

## Copyright
Copyright © 2026 Toni Akinjiola

All rights reserved except as expressly provided under the applicable license.