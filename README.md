# MCT Trading Bot

[![CI](https://github.com/toniton/ml-crypto-trading/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/toniton/ml-crypto-trading/actions/workflows/ci.yml)
[![linting: pylint](https://img.shields.io/badge/linting-pylint-yellowgreen)](https://github.com/pylint-dev/pylint)
[![codecov](https://codecov.io/github/toniton/ml-crypto-trading/graph/badge.svg?token=N0VBWT87L7)](https://codecov.io/github/toniton/ml-crypto-trading)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Docker pull](https://img.shields.io/docker/pulls/toniton/ml-crypto-trading)](https://hub.docker.com/r/toniton/ml-crypto-trading)

MCT (stands for ML-Crypto-Trading) trading bot is a free and open-source cryptocurrency trading engine written in
Python.

> Caveat Utilitor! For educational and research purposes only.

---

## Quick Start

The easiest way to run the bot is using **Docker**.

### Prerequisites

- **Docker & Docker Compose**: Installed and running on your system.
- **PostgreSQL**: A running instance (local or remote) to store trading history.

### 1. Configuration

Create your asset configuration and environment variables.

**assets.yaml**
```yaml
assets:  
  - name: "Bitcoin (Crypto.com)"
    base_ticker_symbol: "BTC"
    quote_ticker_symbol: "USD"
    exchange: "CRYPTO_DOT_COM"
    min_quantity: 0.00001
    decimal_places: 8
    candles_timeframe: "MIN1"
    schedule: 4
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

#### 📊 Backtesting (Historical Data)

Test your strategy without risking real funds using historical CSV data.
```bash
docker run -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/assets.yaml \
  --backtest-mode=true \
  --backtest-source=/workspace/history/
```

#### 🧪 Simulated Trading (Real-time Paper Trading)

Run the bot with real-time market data but simulate order execution in memory.
```bash
docker run --env-file .env -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/assets.yaml \
  --simulated=true
```

#### 🚀 Live Trading (Real Exchange)

Execute real trades on the configured exchange.
```bash
docker run --env-file .env -v $PWD:/workspace toniton/ml-crypto-trading \
  --assets-conf=/workspace/assets.yaml
```

*For multi-container setups (with Database), check the included `docker-compose.yml`.*

---

## Documentation

For more detailed information, please refer to the documentation in the `docs/` directory:

- [Introduction & Features](docs/introduction.md)
- [Core Concepts](docs/concepts.md)
- [Configuration & System Properties](docs/configuration.md)
- [Architecture & Diagrams](docs/architecture.md)
- [Logging Architecture](docs/logging.md)
- [Community & Contributing](docs/community.md)

---

## License

This source code is available on GitHub under
the [GNU Lesser General Public License v3.0](https://www.gnu.org/licenses/lgpl-3.0.en.html).
