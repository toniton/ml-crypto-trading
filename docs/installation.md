# Installation & Setup Guide

This guide covers installing and bootstrapping the **MCT Trading Engine & Server** across macOS, Linux, and Windows.

---

## 1. Prerequisites

Before installing, ensure your environment meets the minimum requirements:

- **Python**: `3.11+` (Python 3.12 recommended)
- **Database**: PostgreSQL (native local installation, Docker container, or remote managed provider like Supabase, Neon, or AWS RDS)
- **Make** & **Git**: Standard developer toolchains
- **Docker & Docker Compose** *(Optional, for containerized database or headless runs)*

---

## 2. Interactive CLI Setup Wizard (Recommended)

MCT includes an interactive, cross-platform terminal wizard (`installer/`) that guides you through preflight checks, environment configuration, database provisioning, API credentials setup, dependency installation, and database migrations.

### Launching the Wizard

**macOS / Linux:**
```bash
./install.sh
# Or via Make:
make install-interactive
```

**Windows (PowerShell):**
```powershell
.\install.ps1
```

### Installation Steps in the Wizard

1. **Preflight Checks**: Verifies Python version (`>=3.11`), required system tools (`git`, `make`, `docker`), and virtual environment status.
2. **Environment Configuration**: Copies `.env.example` to `.env` if not present, and sets core environment keys (`APP_ENV=development` or `production`).
3. **Database Provisioning**:
   - **Option 1: Existing Remote Database** — Supabase, Neon, or remote PostgreSQL (prompts for host, port, user, password, and database name).
   - **Option 2: Local Docker Database** — Automatically inspects Docker daemon readiness and configures the PostgreSQL container.
   - **Option 3: Local Native Service** — Connects to a locally running PostgreSQL service (`localhost:5432`).
   - **Option 4: Manual / Custom** — Leaves database variables in `.env` for manual editing.
4. **Exchange & LLM Credentials**:
   - Optional interactive entry of Exchange API keys (`CRYPTO_DOT_COM__API_KEY`, etc.).
   - Optional selection of AI model provider (`groq`, `gemini`, `deepseek`, `ollama`) and API keys.
5. **Dependency Installation**: Bootstraps the virtual environment in `.venv/` (or `--venv-dir`) and installs production and development dependencies (`pip install -r requirements.txt -r requirements-dev.txt`).
6. **Database Schema Migrations**: Runs `alembic upgrade head` to apply all database tables (orders, trades, VCS history, runtime incidents, strategy promotion tables).
7. **Verification & Readiness**: Executes environment verification and tests database connectivity.

---

## 3. Automated & Unattended Installation (CI/CD)

The CLI installer supports headless/non-interactive operation with pre-packaged profiles:

```bash
# Quickstart profile (default choices, non-interactive)
./install.sh --non-interactive --profile=quickstart

# Developer profile (installs development dependencies and pre-commit hooks)
./install.sh --non-interactive --profile=developer

# Production profile
./install.sh --non-interactive --profile=production

# Dry-run mode (simulates changes without modifying files or running commands)
./install.sh --dry-run
```

### Command-Line Arguments

| Flag | Description | Default |
| :--- | :--- | :--- |
| `--non-interactive` | Run without interactive prompts using defaults and flags | `false` |
| `--profile` | Configuration profile: `quickstart`, `developer`, `production`, `custom` | `quickstart` |
| `--dry-run` | Simulate installation without writing files or running commands | `false` |
| `--skip-deps` | Skip `pip install` dependency installation | `false` |
| `--skip-db` | Skip database provisioning and connection checks | `false` |
| `--skip-migrations` | Skip running `alembic upgrade head` | `false` |
| `--venv-dir` | Custom path to virtual environment directory | `.venv` |

---

## 4. Manual / Traditional Setup

If you prefer to configure your environment step-by-step:

### Step 1: Create Virtual Environment
```bash
make venv
source .venv/bin/activate
```

### Step 2: Configure Environment Variables
Copy the template and edit your `.env`:
```bash
cp .env.example .env
```

Key environment variables:
```dotenv
APP_ENV=production
DATABASE_CONNECTION_HOST=localhost:5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_DATABASE=trading

# Exchange Credentials (if trading live)
CRYPTO_DOT_COM__API_KEY=your_key
CRYPTO_DOT_COM__SECRET_KEY=your_secret

# LLM Providers (if using AI assistant)
GROQ_API_KEY=your_groq_key
GEMINI_API_KEY=your_gemini_key
```

### Step 3: Provision Database & Run Migrations
```bash
# Check database readiness
make db-setup

# Start local PostgreSQL container (if using Docker)
make db-up

# Apply schema migrations
make upgrade
```

---

## 5. Verification & Testing

Verify that your installation is working properly:

```bash
# Run test suite
make test

# Run linting
make lint

# Run in simulated paper-trading mode
make run-simulated
```

For detailed command options and runtime modes, see [Core Concepts](concepts.md) and [Configuration Guide](configuration.md).
