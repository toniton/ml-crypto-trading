VENV_DIR := ./venv
PYTHON := $(VENV_DIR)/bin/python3
PIP := $(VENV_DIR)/bin/pip
PYLINT := $(VENV_DIR)/bin/pylint
ALEMBIC := $(VENV_DIR)/bin/alembic
PYTEST := $(VENV_DIR)/bin/pytest
PRE_COMMIT := $(VENV_DIR)/bin/pre-commit
DEFAULT_CONFIG := examples/configurations/trading-config.yaml
BACKTEST_CONFIG := examples/configurations/backtest-trading-config.yaml
BACKTEST_SOURCE := examples/coinmarketcap/history

.PHONY: help setup venv install install-dev clean db-up db-down db-setup migrate upgrade downgrade format lint test test-agent-20q test-agent-50q test-50q test-agent-adversarial benchmark-agent benchmark-agent-live benchmark-50q benchmark-50q-live benchmark-50q-live-http run-simulated run-backtest run-live run-headless start

help:
	@echo "Available commands:"
	@echo "  make setup          - Set up virtual environment and install all dependencies"
	@echo "  make venv           - Create virtualenv and install development dependencies"
	@echo "  make install        - Install production dependencies"
	@echo "  make install-dev    - Install development dependencies"
	@echo "  make clean          - Remove virtualenv, cache, and test artifacts"
	@echo "  make db-up          - Start PostgreSQL container via docker-compose"
	@echo "  make db-down        - Stop PostgreSQL container via docker-compose"
	@echo "  make db-setup       - Check database environment (PostgreSQL / Docker) and readiness"
	@echo "  make migrate        - Generate new Alembic migration (pass m='message')"
	@echo "  make upgrade        - Apply pending database migrations"
	@echo "  make downgrade      - Rollback database migrations to base"
	@echo "  make format         - Run code formatter and pre-commit hooks"
	@echo "  make lint           - Run pylint checks"
	@echo "  make test           - Run pytest suite with coverage"
	@echo "  make test-agent-20q - Run Rio 20-Question Acceptance & Grounding pytest suite"
	@echo "  make test-agent-50q - Run Rio 50-Question regression benchmark pytest suite"
	@echo "  make test-agent-adversarial - Run Rio Adversarial Robustness benchmark suite"
	@echo "  make benchmark-agent - Generate Rio benchmark report with adversarial suite (Markdown + JSON)"
	@echo "  make benchmark-agent-live - Run live model quality gate evaluation across trials and archive report"
	@echo "  make benchmark-50q  - Run Rio 50-Question deterministic benchmark and generate reports"
	@echo "  make benchmark-50q-live - Run Rio 50-Question live LLM evaluation across categories"
	@echo "  make benchmark-50q-live-http - Run Rio 50-Question live HTTP evaluation against running API server"
	@echo "  make run-simulated  - Run bot in paper trading / simulated mode"
	@echo "  make run-backtest   - Run bot in backtesting mode"
	@echo "  make run-live       - Run bot in live trading mode (with API server)"
	@echo "  make run-headless   - Run bot in headless live mode (API server disabled)"
	@echo "  make start          - Alias for run-live"

setup:
	@./scripts/setup.sh

venv: $(VENV_DIR)/bin/activate

$(VENV_DIR)/bin/activate: requirements.txt requirements-dev.txt
	@python3 -m venv $(VENV_DIR)
	@$(PIP) install --upgrade pip
	@$(PIP) install -r requirements-dev.txt
	@touch $(VENV_DIR)/bin/activate

install: $(VENV_DIR)/bin/activate
	@$(PIP) install -r requirements.txt

install-dev: $(VENV_DIR)/bin/activate
	@$(PIP) install -r requirements-dev.txt

clean:
	rm -rf $(VENV_DIR)
	rm -rf .pytest_cache .coverage coverage.xml
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

db-up:
	docker compose up -d postgres

db-down:
	docker compose stop postgres

db-setup:
	@./scripts/db_setup.sh

migrate:
	$(ALEMBIC) revision --autogenerate -m "$(or $(m),Migration)"

upgrade:
	$(ALEMBIC) upgrade head

downgrade:
	$(ALEMBIC) downgrade base

format:
	$(PRE_COMMIT) run --all-files

lint: .pylintrc
	$(PYLINT) src tests main.py --rcfile=.pylintrc --fail-on=E,unused-import --fail-under=9.7

test:
	export PYTHONPATH=. && $(PYTEST) tests/ --cov --cov-branch --cov-report=xml -s

test-agent-20q:
	export PYTHONPATH=. && $(PYTEST) tests/benchmark/agent_20q/test_twenty_questions_ci.py -v

test-agent-adversarial:
	export PYTHONPATH=. && $(PYTEST) tests/benchmark/agent_20q/test_adversarial_suite.py -v

benchmark-agent:
	export PYTHONPATH=. && $(PYTHON) ./scripts/benchmark_rio_20q.py --include-adversarial --output-md docs/benchmarks/rio-20q-baseline.md --output-json docs/benchmarks/rio-20q-baseline.json --archive

benchmark-agent-live:
	export PYTHONPATH=. && $(PYTHON) ./scripts/benchmark_rio_20q.py --mode live --include-adversarial --archive $(ARGS)

test-agent-50q:
	export PYTHONPATH=. && $(PYTEST) tests/benchmark/agent_50q/test_fifty_questions_ci.py -v

test-50q: test-agent-50q

benchmark-50q:
	export PYTHONPATH=. && $(PYTHON) ./scripts/benchmark_rio_50q.py --mode deterministic --output-md docs/benchmarks/rio-50q-baseline.md --output-json docs/benchmarks/rio-50q-baseline.json --archive $(ARGS)

benchmark-50q-live:
	export PYTHONPATH=. && $(PYTHON) ./scripts/benchmark_rio_50q.py --mode live --archive $(ARGS)

benchmark-50q-live-http:
	export PYTHONPATH=. && $(PYTHON) ./scripts/benchmark_rio_50q.py --mode live-http --target http://127.0.0.1:8000/api/v1/chat --archive $(ARGS)

run-simulated:
	$(PYTHON) ./main.py --assets-conf=$(DEFAULT_CONFIG) --simulated=true

run-backtest:
	$(PYTHON) ./main.py --assets-conf=$(BACKTEST_CONFIG) --backtest-mode=true --backtest-source=$(BACKTEST_SOURCE)

run-live:
	$(PYTHON) ./main.py --assets-conf=$(DEFAULT_CONFIG) $(ARGS)

run-headless:
	$(PYTHON) ./main.py --assets-conf=$(DEFAULT_CONFIG) --headless=true $(ARGS)

start: run-live