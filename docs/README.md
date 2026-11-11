# MCT Documentation Hub

Welcome to the **MCT (ML-Crypto-Trading)** technical documentation portal.

---

## 🧭 Documentation Index

### 1. 🚀 Getting Started & Configuration
- [**Installation & Setup Guide**](installation.md) — Interactive CLI setup wizard (`install.sh`, `install.ps1`), unattended profiles (`quickstart`, `developer`), PostgreSQL database provisioning, and verification steps.
- [**Run Modes Guide**](run-modes.md) — Simulated paper trading, historical backtesting with friction modeling, live execution, headless daemon, and standalone API server.
- [**Configuration & System Properties**](configuration.md) — Command-line flags, environment variables, YAML specifications (`trading-config.yaml`, `llm.yaml`, `strategies.yaml`), and multi-asset definitions.

### 2. 🧠 Core Concepts & Financial Logic
- [**Introduction & Motivation**](introduction.md) — Architectural motivation, design goals, and high-level feature breakdown.
- [**Core Concepts**](concepts.md) — Byzantine Fault Tolerant (BFT) consensus models (1-of-1, 1-of-2, 2-of-2), Dynamic Expressions syntax, execution friction modeling, and VCS history.
- [**Strategy Promotion Pipeline**](strategy-promotion.md) — Guarded strategy promotion workflow: simulation replay, baseline comparison, drift limits, evaluation policy, and automated VCS staging.

### 3. 🏗️ Architecture & Subsystems
- [**Architecture & Diagrams**](architecture.md) — System flow, dependency injection root, manager container layer, and LangGraph multi-agent subgraphs.
- [**Agent Automation & Monitoring**](agent-automation.md) — Starvation Watchdog, event bus contracts, deterministic anomaly investigation, action safety classes, and asynchronous human-in-the-loop approvals.
- [**Data Retention Policy & Inventory**](retention-inventory.md) — Phase-by-phase storage mapping, TTL policies per table, and cleanup automation.

### 4. 🌐 API & Observability
- [**REST API & WebSocket Reference**](api.md) — Comprehensive directory of all HTTP endpoints (AI chat, VCS, backtests, branches, proposals, metrics) and WebSocket streaming protocols.
- [**Logging Architecture**](logging.md) — Application and trading log streams, structured consensus decision logging, and audit replay.
- [**Benchmarks & Baseline Reports**](benchmarks/rio-20q-baseline.md) — 20q and 50q evaluation baselines, LLM decision grading, and runtime execution metrics.

### 5. 🤝 Community & Governance
- [**Community & Contributing**](community.md) — Discord community, pull request guidelines, and inspiration projects.

---

## 🎯 Role-Based Reading Tracks

### For Traders & Quants
1. Start with [**Configuration Guide**](configuration.md) to understand `trading-config.yaml`.
2. Master the consensus models and formula syntax in [**Core Concepts**](concepts.md).
3. Follow the [**Strategy Promotion Pipeline**](strategy-promotion.md) to safely test and deploy new strategies.

### For Software Engineers & Contributors
1. Review [**Architecture & Diagrams**](architecture.md) to understand component boundaries and manager containers.
2. Read [**Agent Automation & Monitoring**](agent-automation.md) for event-driven contracts and background workers.
3. Review [**REST API & WebSocket Reference**](api.md) and [**Contributing Guidelines**](community.md).

### For DevOps & Operators
1. Read the [**Installation Guide**](installation.md) for automated profiles and container setup.
2. Review [**Logging Architecture**](logging.md) and [**Data Retention Inventory**](retention-inventory.md) for disk and database maintenance.
