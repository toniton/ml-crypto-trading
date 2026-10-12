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
- 🛰️ **Autonomous Trading Activity Monitoring**: A background *Starvation Watchdog* tracks per-asset activity (market data, strategy evaluation, signals, orders, executions) and autonomously raises a structured trading-activity anomaly when an asset goes silent — without waiting for a user prompt.
- ⚙️ **Event-Driven Agent Automation**: The server is a thin transport layer; agentic automation (watchdog, action planning, approvals, investigation) communicates with it purely over an event bus. Events are projected into read models and the chat by an idempotent `AgentEventProjector`.
- 🔐 **Asynchronous Human-in-the-Loop Actions & Approvals**: Mutating REST commands return `202 Accepted` with a `request_id`; the final outcome (commit hash, structured error codes like `BASE_COMMIT_CHANGED`) streams back over WebSocket as `agent_action_*` / `agent_approval_*` events.
- 📐 **Dynamic Expression Engine**: Define position sizing and custom strategy logic using spreadsheet formulas (`rsi`, `sma`, `ema`, `balance`, `equity`, `pnl`, etc.).
- 🤝 **BFT Consensus Engine**: Flexible multi-strategy quorum voting supporting 1-of-1 single strategy, 1-of-2 independent triggers, and 2-of-2 strict consensus.
- 📊 **High-Fidelity Backtesting**: Multi-asset independent clock simulation with realistic execution frictions (slippage, latency, fees), **live drift detection** (`BacktestDriftDetector` compares live journal fills against a backtest replay), walk-forward testing, and tick replay.
- 🌐 **REST API & Real-Time WebSockets**: FastAPI server providing chat streaming, order analytics, monthly heatmaps, latency metrics, agent actions/approvals, configuration proposals, agent/log/health event streaming via WebSocket.
- 📈 **Runtime Observability & Metrics**: Built-in collectors for CPU/memory usage, WebSocket health, order lifecycle timings, exchange telemetry, plus a runtime-debug **incident investigation** subsystem and a decision-history timeline.
- 📜 **Configuration Version Control (VCS)**: Git-like history tracking, audit trail, and rollback for runtime configuration changes.

---

## Agent Automation & Monitoring

The bot ships with an autonomous agent automation subsystem that detects trading anomalies and reacts **without manual prompting**.

> **Design principle:** *Automation detects and decides; events communicate; projectors persist/read-model; the UI presents and requests decisions; VCS/Trading/Backtest perform the approved operation.*

### Architecture

```
                           EventBus
                              │
              ┌───────────────┴────────────────┐
              │                                │
          Transport (server)              Automation
              │                                │
      AgentEventProjector            AutomationController
    (read models + chat + WS)      (watchdog · planner · approvals)
```

- **Starvation Watchdog** (`src/agent/monitoring/`) — polls per-asset activity (market data, strategy evaluation, signals, orders, executions) tracked by the `AssetActivityTracker` and emits `trading_activity_anomaly_detected` when a configured asset exceeds its inactivity threshold (derived from the asset's trading schedule).
- **AutomationController** (`src/agent/automation/`) — consumes anomaly + command events on a dedicated worker queue, runs a deterministic investigation (`InvestigateActivityAnomaly`), decides what to do, and drives the `AgentActionExecutor`.
- **Safety classification** (`ActionSafetyClass`) — every autonomous action is classified `INFORMATIONAL · DIAGNOSTIC · PROPOSAL · STATE_CHANGING · TRADING_CONTROL`. Autonomous monitors are, by default, permitted only informational/diagnostic/proposal actions; **state-changing and trading-control actions are prohibited** unless explicitly granted.
- **Projection** — the server's `AgentEventProjector` treats the event as the source of truth: it is **idempotent** (deduplicated by `event_id`) and materialises events into the conversation store, the chat UI, and in-memory action/approval read models. Events are also streamed to the frontend over the `/api/v1/agent/ws` WebSocket.

### Autonomous workflow

```
Watchdog detects inactivity
   │  TradingActivityAnomalyDetectedEvent
   ▼
InvestigateActivityAnomaly            # deterministic, no LLM
   │  (market data? evaluations? signals? orders/executions?)
   ▼
Automation decision
   ├── Send Drift Diagnostic chat message           (INFORMATIONAL)
   ├── Raise an Approval Proposal to pause the asset (PROPOSAL, e.g. assets.X.enabled=false)
   └── escalate to a runtime incident                (subject to authority)
   │
   ▼
VCS / Backtest services perform the approved operation
```

### Agent REST endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/agent/actions` | Plan/execute an agent action. Returns `202 {request_id, status:"accepted"}`; lifecycle streams over WS. |
| `GET` | `/api/v1/agent/actions` | List actions (projected read model). |
| `GET` | `/api/v1/agent/actions/{id}` | Get a single action. |
| `GET` | `/api/v1/agent/approvals` | List approval requests. |
| `GET` | `/api/v1/agent/approvals/{id}` | Get an approval request. |
| `POST` | `/api/v1/agent/approvals/{id}/decision` | Approve/reject. Returns `202`; the commit hash or structured `error_code`/`error_message` arrives over WS. |
| `POST` | `/api/v1/agent/backtest/compare` | Synchronous backtest drift/config comparison between two commits. |
| `WS` | `/api/v1/agent/ws` | Streams `agent_message_created`, `agent_action_*`, `agent_approval_requested/resolved`, `trading_activity_anomaly_detected`. |

---

## REST API

The FastAPI server exposes the following namespaces (full route inventory in `src/server/app.py`):

| Namespace | Endpoints | Purpose |
| :--- | :--- | :--- |
| `/api/v1/chat` | `POST` | Streaming (SSE) conversational agent chat. |
| `/api/v1/sessions` | `GET`, `GET /{id}`, `GET /{id}/messages` | Conversation sessions. |
| `/api/v1/proposals/{message_id}/decision` | `POST` | Approve/reject an AI configuration proposal. |
| `/api/v1/config`, `/api/v1/configuration` | `GET`/`POST`, `GET /options` | Read/commit runtime configuration. |
| `/api/v1/vcs` | `GET /log`, `GET /checkout/{hash}` | Configuration history & checkout. |
| `/api/v1/agent/...` | — | Agent actions, approvals, drift comparison, WebSocket. |
| `/api/v1/backtests` | — | Run/list backtests, datasets, recorded data. |
| `/api/v1/backtests/branches` | — | Backtest branch preview, create, merge. |
| `/api/v1/runtime` | `GET` | Runtime metrics snapshot. |
| `/api/v1/orders` | `GET /lifecycle`, `GET /{y}/{m}/{d}`, latency & week | Order analytics. |
| `/api/v1/heatmap/orders/{y}/{m}` | `GET` | Monthly order heatmap. |
| `/api/v1/logs/ws` | `WS` | Live log streaming. |

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
- [Agent Automation & Monitoring](docs/agent-automation.md) — Watchdog, event-driven automation, safety classification, and the async approval lifecycle.
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