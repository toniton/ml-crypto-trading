# Introduction

## Motivation

The intent of MCT is to provide a modular trading architecture that combines clean engineering practices with financial
domain logic. It aims to create a flexible environment where developers and traders can collaborate, experiment, and
extend trading strategies with clarity and minimal complexity.

## Core Features (Currently Supported)

### Multi-Asset Support & Scheduling
Trade and manage multiple assets concurrently across supported exchanges. Each asset operates on an independent cadence (from seconds to minutes, hours, or days).

### Dynamic Position Sizing
Calculate dynamic order quantities using spreadsheet-style mathematical expressions. Real-time context exposes technical indicators (`rsi`, `sma`, `ema`), account equity, balance, unrealized PnL, volatility range, and strategy confidence directly in the expression.

### Byzantine Fault Tolerant (BFT) Consensus
A multi-strategy decision engine enabling cooperative trading decisions:
- **Single Strategy (1-of-1)**: Direct execution from an individual strategy rule.
- **Multi Strategy (1-of-2 — OR logic)**: Trade independently whenever *any* strategy triggers.
- **Multi Strategy (2-of-2 — Quorum logic)**: Trade strictly when *all* strategies reach consensus agreement.

### AI Agent & LangGraph Workflows
An intelligent multi-agent conversational assistant powered by LangGraph with modular subgraphs:
- **Router Graph**: Routes intents (configuration, backtest, analytics, account queries).
- **Configuration Graph**: Proposes strategy changes, runs safety validations, computes diffs, and manages human-in-the-loop approval.
- **Backtest Graph**: Runs historical simulations, sweeps parameters, and summarizes risk/return metrics.
- **Performance Analytics Graph**: Analyzes trade distributions, win rates, and order latencies.
- **Trading Oracle**: Generates automated market summaries and performance insights.
- **Multi-Model Support**: Integrated with Groq, Google Gemini, DeepSeek, and Ollama.

### High-Fidelity Backtesting & Simulation
- **Multi-Asset Simulation**: Independent virtual clocks (`BacktestClock`) simulating realistic multi-market conditions.
- **Execution Friction Modeling**: Configurable order latency (`--backtest-latency-ms`), tick slippage (`--backtest-slippage-ticks`), and exchange fee rates (`--backtest-fee-rate`).
- **Drift Detection**: Automatic detection of market regime drift and strategy decay.
- **Isolated DB**: Uses an in-memory `NoopDatabaseManager` to prevent polluting live trade records during backtests.
- **Deterministic Replay**: Replay recorded live ticks (`MarketDataRecorder`) or historical CSV data.

### REST API & Real-Time WebSockets Server
FastAPI-powered backend offering:
- **Chat Streaming**: SSE `/api/v1/chat` endpoint for live conversational trading assistance.
- **Order Analytics**: Heatmaps (`/api/v1/heatmap/orders/...`), daily breakdowns, and execution latency analysis.
- **Proposal Lifecycle**: Endpoints to review, approve, or reject AI configuration proposals.
- **Live WebSocket Streaming**: Stream application and trade logs via `/api/v1/logs/ws`.

### Observability & Runtime Metrics
- Process telemetry (CPU and memory usage collectors).
- Exchange connectivity and WebSocket error monitoring.
- Order lifecycle metrics tracking time-to-fill, fill prices, and slippage.

### Configuration Version Control (VCS)
Git-like content-addressable history tracking for all configuration changes with instant rollback and audit logging.

### Supported Exchanges
- [Crypto.com Exchange](https://crypto.com/exchange)
- CCXT-compatible exchanges (e.g. Binance)
- In-memory Simulated Client for paper trading and backtesting

---

## Join the Community

Interested in contributing or learning more? Join us on [Discord](https://discord.gg/vZh8w3Sz)!

