# Introduction

## Motivation

The intent of MCT is to provide a modular trading architecture that combines clean engineering practices with financial
domain logic. It aims to create a flexible environment where developers and traders can collaborate, experiment, and
extend trading strategies with clarity and minimal complexity.

## Core Features (Currently Supported)

### Multi-Asset Support

Trade and manage multiple assets seamlessly across supported exchanges.

### Dynamic Position Sizing

The engine supports dynamic calculation of trade quantities using a built-in expression parser. This allows users to
incorporate market volatility, balances, and technical indicators (RSI, EMA, SMA) directly into their position sizing
logic.

### Consensus Strategy

Multi-strategy decision engine powered by a Byzantine Fault Tolerant (BFT) voting mechanism.

### Intelligent Trading Scheduler

Trading scheduler gives you control over the frequency each asset trades: every second to every minute, hour, or day.

### Audit Log Replay

Audit logs can be replayed through the backtesting system.

### Trading mode

- Spot trading

### Supported Exchanges

- [Crypto.com Exchange](https://crypto.com/exchange)

### Simulated Trading

You can run the bot in simulated mode, where order placement is intercepted and executed in-memory without hitting the
real exchange.

---

## Join the Community

Interested in contributing or learning more? Join us on [Discord](https://discord.gg/vZh8w3Sz)!

