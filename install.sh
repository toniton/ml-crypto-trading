#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# 1. Resolve Python 3.11+ interpreter
PYTHON_BIN=""
for candidate in python3 python py; do
    if command -v "${candidate}" &>/dev/null; then
        if "${candidate}" -c 'import sys; exit(0 if sys.version_info >= (3, 11) else 1)' &>/dev/null; then
            PYTHON_BIN="${candidate}"
            break
        fi
    fi
done

if [ -z "${PYTHON_BIN}" ]; then
    echo "Error: Python 3.11+ is required but was not found in PATH." >&2
    echo "Please install Python 3.11 or newer and retry." >&2
    exit 1
fi

# 2. Use existing venv python if available, otherwise host python
VENV_PYTHON="${SCRIPT_DIR}/venv/bin/python"
if [ -x "${VENV_PYTHON}" ]; then
    EXEC_PYTHON="${VENV_PYTHON}"
else
    EXEC_PYTHON="${PYTHON_BIN}"
fi

# 3. Launch interactive installer module
exec "${EXEC_PYTHON}" -m installer "$@"
