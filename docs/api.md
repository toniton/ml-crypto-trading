# REST API & WebSocket Reference

The MCT backend includes an integrated FastAPI HTTP server and real-time WebSocket subsystem. 

---

## 1. Server Overview

Start the server using:
```bash
python main.py --server=true --api-port=8000
# Or via Make
make run-live
```

Base URL: `http://localhost:8000` (or configured host/port)  
Interactive OpenAPI / Swagger Docs: `http://localhost:8000/docs`

---

## 2. API Namespaces & Endpoint Directory

### 2.1 Conversational AI & Sessions
Interact with the LangGraph multi-agent trading assistant.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/chat` | Server-Sent Events (SSE) streaming chat endpoint. Accepts `{ message: string, session_id?: string }`. |
| `GET`  | `/api/v1/sessions` | List recent conversation sessions. |
| `GET`  | `/api/v1/sessions/{session_id}` | Retrieve full message history for a given session. |
| `POST` | `/api/v1/sessions/{session_id}/messages` | Append a message to an existing session. |
| `POST` | `/api/v1/proposals/{message_id}/decision` | Approve or reject a pending AI configuration proposal. |

---

### 2.2 Configuration & Version Control (VCS)
Inspect, update, and audit runtime configurations.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET`  | `/api/v1/config` (or `/api/v1/configuration`) | Retrieve active runtime configuration YAML/JSON. |
| `POST` | `/api/v1/config` (or `/api/v1/configuration`) | Commit new configuration with commit message. |
| `GET`  | `/api/v1/config/options` | Retrieve available exchanges, timeframes, and built-in strategies. |
| `GET`  | `/api/v1/vcs/log` | Query VCS commit history, commit hashes, and authorship. |
| `GET`  | `/api/v1/vcs/checkout/{commit_hash}` | Inspect configuration state at a historical commit. |

---

### 2.3 Agent Automation & Human-in-the-Loop Approvals
Event-driven autonomous monitoring, watchdog anomaly investigation, and action execution.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/agent/actions` | Plan or execute an action. Returns `202 Accepted` with `request_id`; status streams over WebSocket. |
| `GET`  | `/api/v1/agent/actions` | List all historical and pending agent actions. |
| `GET`  | `/api/v1/agent/actions/{id}` | Retrieve details and execution logs for an action. |
| `GET`  | `/api/v1/agent/approvals` | List pending approval requests. |
| `GET`  | `/api/v1/agent/approvals/{id}` | Retrieve details of a specific approval request. |
| `POST` | `/api/v1/agent/approvals/{id}/decision` | Approve or reject an action. Returns `202 Accepted`. |
| `POST` | `/api/v1/agent/backtest/compare` | Synchronous backtest drift comparison between two commits. |
| `WS`   | `/api/v1/agent/ws` | Real-time WebSocket streaming agent events, anomaly alerts, and approvals. |

---

### 2.4 Strategy Promotion Pipeline
Guarded promotion of simulated strategies into production.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/promotion/evaluate` | Submits a configuration candidate for simulated execution and comparison. |
| `GET`  | `/api/v1/promotion/candidates` | Lists all active promotion candidates and evaluation statuses. |
| `GET`  | `/api/v1/promotion/candidates/{id}` | Retrieves full metrics, simulation telemetry, and diff for a candidate. |
| `POST` | `/api/v1/promotion/candidates/{id}/decision` | Approves or rejects a promotion proposal. |
| `GET`  | `/api/v1/promotion/history` | Historical audit log of past promotions. |

---

### 2.5 Backtesting & Virtual Branching
Historical simulation, parameter sweeps, and branch configuration isolation.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET`  | `/api/v1/backtests` | List past backtest sessions and summary results. |
| `POST` | `/api/v1/backtests` | Start a new backtest simulation session. |
| `GET`  | `/api/v1/backtests/{session_id}` | Retrieve status and metrics for a backtest session. |
| `POST` | `/api/v1/backtests/{session_id}/cancel` | Cancel an ongoing backtest session. |
| `GET`  | `/api/v1/backtests/datasets` | List available historical market datasets. |
| `POST` | `/api/v1/backtests/datasets` | Upload a new historical market dataset CSV. |
| `GET`  | `/api/v1/backtests/recorded-data` | List recorded live market observations available for replay. |
| `GET`  | `/api/v1/backtests/branches` | List virtual configuration branches. |
| `POST` | `/api/v1/backtests/branches` | Create a new configuration branch for isolated experimentation. |
| `GET`  | `/api/v1/backtests/branches/{id}/configuration` | Retrieve configuration for a specific branch. |
| `PUT`  | `/api/v1/backtests/branches/{id}/configuration/assets/{symbol}` | Update asset strategy parameters in a branch. |
| `POST` | `/api/v1/backtests/branches/{id}/merge-preview` | Compute diff and preview merge into main configuration. |
| `POST` | `/api/v1/backtests/branches/{id}/merge` | Merge branch configuration into production VCS. |

---

### 2.6 Dynamic Expression Engine
Real-time mathematical formula validation and testing.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/expressions/evaluate` | Evaluates a formula (e.g. `rsi(14) < 30`) against mock or live market data. |
| `GET`  | `/api/v1/expressions/functions` | Lists supported mathematical and financial functions. |

---

### 2.7 Observability, Orders & Analytics
Runtime health, execution telemetry, and trade performance.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET`  | `/api/v1/runtime` | Snapshot of CPU, memory, uptime, and thread status. |
| `GET`  | `/api/v1/orders/lifecycle` | Detailed order state transition latencies and fill metrics. |
| `GET`  | `/api/v1/heatmap/orders/{year}/{month}` | Calendar heatmap matrix of order counts and volume. |
| `GET`  | `/api/v1/orders/{year}/{month}/{day}` | Detailed list of orders executed on a specific date. |
| `GET`  | `/api/v1/orders/latency/{year}/{month}` | Order execution latency distribution and percentiles. |
| `GET`  | `/api/v1/performance/assets/{ticker}` | Cumulative returns, Sharpe ratio, and drawdown for an asset. |
| `GET`  | `/api/v1/performance/attribution/{ticker}` | Returns attribution by strategy component. |

---

### 2.8 Data Retention & Storage Policy
Storage management and cleanup policies.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET`  | `/api/v1/retention/status` | Current database row counts and disk storage usage by data category. |
| `POST` | `/api/v1/retention/run` | Triggers on-demand execution of data retention cleanup policies. |

---

## 3. Real-Time WebSocket Protocols

### 3.1 Live Log Stream (`/api/v1/logs/ws`)
Streams live log events emitted by the engine and API server.

**Message Format (JSON):**
```json
{
  "timestamp": "2026-11-10T08:15:00.123Z",
  "level": "INFO",
  "logger": "trading.executor",
  "message": "Consensus reached for BTC/USD: BUY with score 1.5",
  "context": {
    "asset": "BTC/USD",
    "action": "BUY"
  }
}
```

### 3.2 Agent Event Stream (`/api/v1/agent/ws`)
Streams agent automation updates, anomaly detection alerts, and approval requests.

**Event Types:**
- `agent_message_created`: Streaming or finalized chat message.
- `agent_action_started` / `agent_action_completed` / `agent_action_failed`: Asynchronous action execution status.
- `agent_approval_requested`: New human-in-the-loop decision requested (e.g., pause asset).
- `agent_approval_resolved`: Confirmation of approved or rejected decision.
- `trading_activity_anomaly_detected`: Starvation watchdog alert when an asset has gone silent.
