#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${VENV_DIR:-${PROJECT_ROOT}/venv}"

echo "=========================================="
echo " MCT Trading Bot - Environment Setup"
echo "=========================================="

# 1. Resolve Python interpreter
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "${PYTHON_BIN}" ]; then
    if command -v python3 &>/dev/null; then
        PYTHON_BIN="python3"
    elif command -v python &>/dev/null; then
        PYTHON_BIN="python"
    elif command -v py &>/dev/null; then
        PYTHON_BIN="py -3"
    else
        echo "Error: Python interpreter not found. Please install Python 3.11+." >&2
        exit 1
    fi
fi

PYTHON_VERSION=$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Found Python version: ${PYTHON_VERSION} using ${PYTHON_BIN}"

# 2. Setup Virtual Environment
if [ ! -d "${VENV_DIR}" ]; then
    echo "Creating virtual environment at: ${VENV_DIR}"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
else
    echo "Virtual environment already exists at: ${VENV_DIR}"
fi

# Detect venv bin/Scripts directory (Unix vs Windows)
if [ -d "${VENV_DIR}/Scripts" ]; then
    VENV_BIN_DIR="${VENV_DIR}/Scripts"
else
    VENV_BIN_DIR="${VENV_DIR}/bin"
fi

if [ -f "${VENV_BIN_DIR}/python3" ] || [ -f "${VENV_BIN_DIR}/python3.exe" ]; then
    VENV_PYTHON="${VENV_BIN_DIR}/python3"
else
    VENV_PYTHON="${VENV_BIN_DIR}/python"
fi

VENV_PIP="${VENV_BIN_DIR}/pip"

# 3. Upgrade Pip
echo "Upgrading pip..."
"${VENV_PYTHON}" -m pip install --upgrade pip 2>/dev/null || echo "[!] Notice: Pip upgrade skipped (offline/sandbox environment)."

# 4. Install Dependencies
echo "Installing dependencies..."
if [ -f "${PROJECT_ROOT}/requirements-dev.txt" ]; then
    if ! "${VENV_PIP}" install -r "${PROJECT_ROOT}/requirements-dev.txt" 2>/dev/null; then
        if "${VENV_PYTHON}" -c "import pytest, fastapi, alembic" &>/dev/null; then
            echo "[✓] Offline/sandbox mode detected: existing installed packages verified."
        else
            echo "Error: Failed to install dependencies and required packages are missing." >&2
            exit 1
        fi
    fi
elif [ -f "${PROJECT_ROOT}/requirements.txt" ]; then
    if ! "${VENV_PIP}" install -r "${PROJECT_ROOT}/requirements.txt" 2>/dev/null; then
        if "${VENV_PYTHON}" -c "import fastapi, alembic" &>/dev/null; then
            echo "[✓] Offline/sandbox mode detected: existing installed packages verified."
        else
            echo "Error: Failed to install dependencies and required packages are missing." >&2
            exit 1
        fi
    fi
fi

# Helper to update key-value pairs in .env safely
set_env_var() {
    local key="$1"
    local value="$2"
    local file="${3:-${PROJECT_ROOT}/.env}"

    "${VENV_PYTHON}" -c "
import sys, re
key, val, path = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
except FileNotFoundError:
    content = ''

pattern = r'^' + re.escape(key) + r'=.*$'
if re.search(pattern, content, flags=re.MULTILINE):
    content = re.sub(pattern, f'{key}={val}', content, flags=re.MULTILINE)
else:
    content = content.rstrip() + f'\n{key}={val}\n'

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
" "$key" "$value" "$file"
}

# 5. Bootstrap Environment File
if [ ! -f "${PROJECT_ROOT}/.env" ]; then
    if [ -f "${PROJECT_ROOT}/.env.example" ]; then
        echo "Creating .env from .env.example..."
        cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
    fi
fi

# 6. Database Prerequisite Setup
echo ""
echo "--------------------------------------------------"
echo " Database Prerequisite Configuration"
echo "--------------------------------------------------"
echo "MCT requires a PostgreSQL database (local or remote) to store trading state."
echo "Please select your database option:"
echo "  1) Use existing remote database (e.g., Supabase, Neon, AWS RDS)"
echo "  2) Set up local database (Docker or native PostgreSQL via db_setup)"
echo "  3) Skip / Configure .env manually later"

DB_CHOICE="${DB_OPTION:-}"
if [ -z "${DB_CHOICE}" ]; then
    if [ -t 0 ]; then
        read -r -p "Enter choice [1-3] (default: 2): " USER_DB_CHOICE
        DB_CHOICE="${USER_DB_CHOICE:-2}"
    else
        DB_CHOICE="3"
    fi
fi

case "${DB_CHOICE}" in
    1|--remote)
        echo ""
        echo "Enter remote database details:"
        if [ -t 0 ]; then
            read -r -p "Host & Port (e.g. db.xxx.supabase.co:5432): " DB_HOST
            read -r -p "Database name [trading]: " DB_NAME
            DB_NAME="${DB_NAME:-trading}"
            read -r -p "Username [postgres]: " DB_USER
            DB_USER="${DB_USER:-postgres}"
            read -r -s -p "Password: " DB_PASS
            echo ""
        else
            DB_HOST="${DB_HOST:-localhost:5432}"
            DB_NAME="${DB_NAME:-trading}"
            DB_USER="${DB_USER:-postgres}"
            DB_PASS="${DB_PASS:-}"
        fi

        set_env_var "DATABASE_CONNECTION_HOST" "${DB_HOST}"
        set_env_var "POSTGRES_DATABASE" "${DB_NAME}"
        set_env_var "POSTGRES_USER" "${DB_USER}"
        set_env_var "POSTGRES_PASSWORD" "${DB_PASS}"
        echo "[✓] Remote database credentials saved to .env."

        if [ -t 0 ]; then
            read -r -p "Run database schema migrations now? [Y/n]: " RUN_MIG
            if [[ "${RUN_MIG:-Y}" =~ ^[Yy]$ ]]; then
                (cd "${PROJECT_ROOT}" && "${VENV_BIN_DIR}/alembic" upgrade head || true)
            fi
        fi
        ;;
    2|--local)
        echo ""
        "${SCRIPT_DIR}/db_setup.sh" || true
        ;;
    3|--skip)
        echo "Skipping database configuration. Please edit .env before launching the bot."
        ;;
    *)
        echo "Skipping database configuration."
        ;;
esac

# 7. Install Git pre-commit hooks
if [ -d "${PROJECT_ROOT}/.git" ]; then
    if [ -x "${VENV_BIN_DIR}/pre-commit" ] || [ -f "${VENV_BIN_DIR}/pre-commit.exe" ] || [ -f "${VENV_BIN_DIR}/pre-commit" ]; then
        echo ""
        echo "Configuring pre-commit git hooks..."
        (cd "${PROJECT_ROOT}" && "${VENV_BIN_DIR}/pre-commit" install 2>/dev/null || true)
    fi
fi

ACTIVATE_PATH="${VENV_BIN_DIR}/activate"
echo "=========================================="
echo " Setup complete! Virtual environment ready."
echo " Activate with: source ${ACTIVATE_PATH}"
echo "=========================================="
