# Run Modes Guide

MCT supports multiple execution modes catering to different phases of the algorithmic trading lifecycle: research, backtesting, paper trading, and live deployment.

---

## 1. Run Modes Overview

| Mode | Purpose | Engine Loop | API / WS Server | Capital at Risk | Default Make Target |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Simulated (Paper Trading)** | Test strategies against real-time live market streams without risking funds | Yes | Yes | **No** | `make run-simulated` |
| **Backtesting** | Historical tick / CSV replay with realistic execution friction modeling | Yes (virtual clock) | No | **No** | `make run-backtest` |
| **Live Trading** | Real-world order execution on configured exchanges | Yes | Yes | **Yes** | `make run-live` |
| **Headless Trading** | Production trading engine daemon running without the web/API layer | Yes | No | **Yes** | `make run-headless` |
| **Server Only** | FastAPI HTTP server, SSE chat, and WebSocket telemetry without trading loops | No | Yes | **No** | `python main.py --server=true` |

---

## 2. Detailed Mode Specifications

### 2.1 🧪 Simulated Trading (Paper Trading)

Simulated mode connects to real exchange WebSockets and public market data endpoints, running strategy evaluation, Dynamic Expressions, and BFT consensus in real time. Orders are executed against an in-memory simulated account.

**Key Characteristics:**
- Real-time exchange ticker and order book data.
- Virtual portfolio balances and fill executions.
- Zero risk to live exchange capital.

**Execution Commands:**
```bash
# Via Make
make run-simulated

# Direct Python CLI
python main.py --assets-conf=trading-config.yaml --simulated=true

# Via Docker
docker run --env-file .env -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/trading-config.yaml \
  --simulated=true
```

---

### 2.2 📊 Backtesting & Historical Replay

Backtesting mode evaluates strategies deterministically against historical data (CSV datasets or recorded live audit logs) using independent per-asset virtual clocks (`BacktestClock`).

**Execution Frictions:**
- **Latency Delay (`--backtest-latency-ms`)**: Simulates network and exchange order processing latency.
- **Tick Slippage (`--backtest-slippage-ticks`)**: Models market impact and bid/ask spread slippage.
- **Fee Rate (`--backtest-fee-rate`)**: Deducts percentage exchange fees per fill.
- **Database Isolation**: Employs an in-memory `NoopDatabaseManager` to prevent polluting production trade records.

**Execution Commands:**
```bash
# Via Make (runs default historical dataset)
make run-backtest

# Direct Python CLI with custom frictions
python main.py \
  --assets-conf=trading-config.yaml \
  --backtest-mode=true \
  --backtest-source=./data/datasets/btc_usd_1m.csv \
  --backtest-latency-ms=250.0 \
  --backtest-slippage-ticks=2 \
  --backtest-fee-rate=0.001

# Replaying recorded live audit log
python main.py \
  --assets-conf=trading-config.yaml \
  --backtest-mode=true \
  --backtest-source=./logs/audit-BTC_USD-2026-01.log

# Via Docker
docker run -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/trading-config.yaml \
  --backtest-mode=true \
  --backtest-source=/workspace/history/ \
  --backtest-latency-ms=500.0 \
  --backtest-slippage-ticks=2 \
  --backtest-fee-rate=0.001
```

---

### 2.3 🚀 Live Trading (Real Exchange)

Live trading connects directly to configured exchanges (e.g. Crypto.com Native API or CCXT-supported exchanges), evaluating consensus rules and dispatching real order executions. It starts the integrated FastAPI server and WebSocket telemetry streams by default.

> [!WARNING]
> Real capital is placed at risk. Ensure credentials, position sizing formulas, and max drawdown protection limits are thoroughly verified in simulation before running live.

**Execution Commands:**
```bash
# Via Make
make run-live

# Direct Python CLI
python main.py --assets-conf=trading-config.yaml

# Via Docker
docker run --env-file .env -p 8000:8000 -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/trading-config.yaml
```

---

### 2.4 🔕 Headless Mode (Core Engine Daemon)

Headless mode runs live or simulated trading operations as a minimal background daemon without binding an HTTP port or running the FastAPI server.

**Use Cases:**
- Embedded environments or resource-constrained background workers.
- Automated systemd services or Docker containers that do not require web UIs.

**Execution Commands:**
```bash
# Via Make
make run-headless

# Direct Python CLI
python main.py --assets-conf=trading-config.yaml --headless=true

# Via Docker
docker run --env-file .env -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/trading-config.yaml \
  --headless=true
```

---

### 2.5 🌐 Standalone API & Agent Server

Starts the FastAPI server, SSE conversational agent endpoint (`/api/v1/chat`), and telemetry WebSockets (`/api/v1/logs/ws`, `/api/v1/agent/ws`) without instantiating the trading loop.

**Use Cases:**
- Dedicated API gateway instances.
- Serving historical reporting, backtest analytics, and chat sessions without running live trading routines.

**Execution Commands:**
```bash
# Direct Python CLI
python main.py --assets-conf=trading-config.yaml --server=true --api-port=8000

# Via Docker
docker run --env-file .env -p 8000:8000 -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/trading-config.yaml \
  --server=true \
  --api-port=8000
```

---

## 3. Command-Line Flag Reference

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--assets-conf` | `string` | `trading-config.yaml` | Path to asset and strategy YAML configuration file |
| `--simulated` | `boolean` | `false` | Enable paper trading mode with in-memory order execution |
| `--backtest-mode` | `boolean` | `false` | Enable historical simulation replay mode |
| `--backtest-source` | `string` | `""` | Path to historical CSV file, directory, or recorded audit log |
| `--backtest-latency-ms` | `float` | `0.0` | Simulated order fill latency delay in milliseconds |
| `--backtest-slippage-ticks` | `int` | `0` | Number of price ticks to slip on simulated market order execution |
| `--backtest-fee-rate` | `float` | `0.0` | Fee rate fraction applied to simulated order fills (e.g. `0.001` = 0.1%) |
| `--headless` | `boolean` | `false` | Run without starting the FastAPI HTTP / WebSocket server |
| `--server` | `boolean` | `true` | Start the FastAPI web and telemetry server |
| `--api-port` | `int` | `8000` | Port for the FastAPI server |

---

## 4. Related Documentation

- [Core Concepts](concepts.md) — BFT consensus model, Dynamic Expressions, and execution friction mathematics.
- [Configuration Guide](configuration.md) — Comprehensive YAML syntax and environment variable options.
- [Installation Guide](installation.md) — Quickstart wizard, profiles, and database setup.
- [REST API Reference](api.md) — Endpoint directory and WebSocket protocols.
