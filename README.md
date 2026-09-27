# MCT Trading Bot

[![CI](https://github.com/toniton/ml-crypto-trading/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/toniton/ml-crypto-trading/actions/workflows/ci.yml)
[![linting: pylint](https://img.shields.io/badge/linting-pylint-yellowgreen)](https://github.com/pylint-dev/pylint)
[![codecov](https://codecov.io/github/toniton/ml-crypto-trading/graph/badge.svg?token=N0VBWT87L7)](https://codecov.io/github/toniton/ml-crypto-trading)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![License: PolyForm Noncommercial](https://img.shields.io/badge/License-PolyForm_Noncommercial_1.0.0-blue.svg)](LICENSE.txt)
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

The bot can be run using **Make / standard Python** or **Docker**.

### Prerequisites

- **Python 3.11+** (or Docker & Docker Compose)
- **PostgreSQL**: A running instance (local Docker, native service, or remote like **Supabase**, **Neon**, **AWS RDS**).
- **Operating System**: macOS, Linux, or Windows (PowerShell, WSL, or Git Bash).

### 1. Automated Setup (Cross-Platform)

The automated setup guides you through dependency installation, environment configuration, and database connection options:

**macOS / Linux / WSL / Git Bash:**
```bash
make setup
# Or directly: ./scripts/setup.sh
```

**Windows (PowerShell):**
```powershell
.\scripts\setup.ps1
```

During setup, you will be prompted to choose how your PostgreSQL database is provisioned:
- **Option 1: Existing Remote Database** — Enter credentials for Supabase, Neon, or remote PostgreSQL; the script configures `.env` and applies schema migrations.
- **Option 2: Local Database Setup** — Automatically launches `db_setup` to detect/install/start local PostgreSQL or a Docker container.
- **Option 3: Manual Configuration** — Skip to configure `.env` manually.

### 2. Configuration & Manual Commands

1. **Environment Variables**: Edit `.env` (copied from `.env.example` during setup):
   ```env
   APP_ENV=production
   DATABASE_CONNECTION_HOST=localhost:5432  # or db.xxxx.supabase.co:5432
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=your_password
   POSTGRES_DATABASE=trading
   CRYPTO_DOT_COM__API_KEY=your_api_key
   CRYPTO_DOT_COM__SECRET_KEY=your_secret_key
   ```

2. **Database Setup & Migrations**: Check database readiness and apply schema migrations:

   **macOS / Linux / WSL:**
   ```bash
   make db-setup  # Checks local PostgreSQL or Docker availability across OS
   make db-up     # Starts PostgreSQL container (if using Docker)
   make upgrade   # Applies Alembic database migrations
   ```

   **Windows (PowerShell):**
   ```powershell
   .\scripts\db_setup.ps1  # Checks PostgreSQL service / Docker status and offers setup guidance
   docker compose up -d postgres
   alembic upgrade head
   ```

3. **Trading Configuration (`trading-config.yaml`)**:
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

---

## Makefile Commands Reference

| Command | Description |
| :--- | :--- |
| `make setup` | Bootstrap virtualenv, install dependencies, init `.env`, and setup git hooks |
| `make venv` | Create virtual environment and install development dependencies |
| `make install` | Install production requirements (`requirements.txt`) |
| `make install-dev` | Install development requirements (`requirements-dev.txt`) |
| `make clean` | Clean virtualenv, pytest cache, coverage files, and python bytecode |
| `make db-setup` | Check database environment (PostgreSQL / Docker) and readiness |
| `make db-up` | Start PostgreSQL container via `docker compose` |
| `make db-down` | Stop PostgreSQL container |
| `make upgrade` | Apply pending Alembic migrations (`alembic upgrade head`) |
| `make downgrade` | Rollback database migrations to base |
| `make migrate` | Generate a new Alembic migration revision (`make migrate m="my migration"`) |
| `make format` | Run pre-commit hooks and code formatters |
| `make lint` | Run pylint checks |
| `make test` | Run pytest suite with code coverage |
| `make run-simulated` | Run paper trading in simulated mode |
| `make run-backtest` | Run historical backtesting simulation |
| `make run-live` | Run live trading engine (with integrated API server) |
| `make run-headless` | Run live trading in headless mode (API server disabled) |

---

## Run Modes

### 🧪 Simulated Trading (Paper Trading)

Run the bot with live market streams while executing simulated orders in memory:

```bash
make run-simulated
```

Or via Docker:
```bash
docker run --env-file .env -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/trading-config.yaml \
  --simulated=true
```

### 📊 Backtesting (Historical Data & Replay)

Test strategies against historical CSV or recorded audit data with realistic execution frictions (slippage, latency, fees):

```bash
make run-backtest
```

Or via Docker:
```bash
docker run -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/trading-config.yaml \
  --backtest-mode=true \
  --backtest-source=/workspace/history/ \
  --backtest-latency-ms=500.0 \
  --backtest-slippage-ticks=2 \
  --backtest-fee-rate=0.001
```

### 🚀 Live Trading (Real Exchange)

Execute live orders on the configured exchange (starts integrated FastAPI & Agent server by default):

```bash
make run-live
```

Or via Docker:
```bash
docker run --env-file .env -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/trading-config.yaml
```

### 🔕 Headless Mode (Core Engine Only)

Run trading operations without starting the FastAPI HTTP / WebSocket server:

```bash
make run-headless
```

Or via Docker:
```bash
docker run --env-file .env -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/trading-config.yaml \
  --headless=true
```

### 🌐 REST API & AI Agent Server

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

## License & Commercial Terms

This project is source-available under the **[PolyForm Noncommercial License 1.0.0](LICENSE.txt)**.

- **Free for Personal & Educational Use**: You are free to view, download, modify, and run this software for non-commercial purposes, personal trading research, and learning.
- **Commercial Restrictions**: Any commercial use, proprietary trading for profit by institutions or funds, hosting MCT as a commercial service/SaaS, or selling software built on MCT requires a separate commercial license from the author.

For commercial licensing inquiries or institutional partnerships, please reach out via [Discord](https://discord.gg/vZh8w3Sz) or open a private inquiry.

## Copyright
Copyright © 2026 Toni Akinjiola. All rights reserved.