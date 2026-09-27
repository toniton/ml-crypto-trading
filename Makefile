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

.PHONY: help setup venv install install-dev clean db-up db-down db-setup migrate upgrade downgrade format lint test run-simulated run-backtest run-live run-headless start

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

run-simulated:
	$(PYTHON) ./main.py --assets-conf=$(DEFAULT_CONFIG) --simulated=true

run-backtest:
	$(PYTHON) ./main.py --assets-conf=$(BACKTEST_CONFIG) --backtest-mode=true --backtest-source=$(BACKTEST_SOURCE)

run-live:
	$(PYTHON) ./main.py --assets-conf=$(DEFAULT_CONFIG) $(ARGS)

run-headless:
	$(PYTHON) ./main.py --assets-conf=$(DEFAULT_CONFIG) --headless=true $(ARGS)

start: run-live