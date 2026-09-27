#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=========================================="
echo " MCT Trading Bot - Database Setup & Runner"
echo "=========================================="

detect_os() {
    case "$(uname -s)" in
        Darwin*)              echo "macOS" ;;
        Linux*)               echo "Linux" ;;
        MINGW*|MSYS*|CYGWIN*) echo "Windows" ;;
        *)
            if [ "${OS:-}" = "Windows_NT" ]; then
                echo "Windows"
            else
                echo "Unknown"
            fi
            ;;
    esac
}

OS_TYPE="$(detect_os)"

is_port_listening() {
    local host="${1:-localhost}"
    local port="${2:-5432}"

    if command -v nc &>/dev/null; then
        nc -z "${host}" "${port}" &>/dev/null
    elif command -v python3 &>/dev/null; then
        python3 -c "import socket; s = socket.socket(); s.settimeout(1); exit(0 if s.connect_ex(('${host}', int(${port}))) == 0 else 1)" &>/dev/null
    elif command -v python &>/dev/null; then
        python -c "import socket; s = socket.socket(); s.settimeout(1); exit(0 if s.connect_ex(('${host}', int(${port}))) == 0 else 1)" &>/dev/null
    else
        return 1
    fi
}

start_local_postgres() {
    echo "Attempting to start local PostgreSQL service..."
    if [ "${OS_TYPE}" = "macOS" ]; then
        if command -v brew &>/dev/null; then
            brew services start postgresql@16 2>/dev/null || brew services start postgresql 2>/dev/null || true
        fi
    elif [ "${OS_TYPE}" = "Linux" ]; then
        if command -v systemctl &>/dev/null; then
            sudo systemctl start postgresql 2>/dev/null || true
        elif command -v service &>/dev/null; then
            sudo service postgresql start 2>/dev/null || true
        fi
    elif [ "${OS_TYPE}" = "Windows" ]; then
        net start postgresql-x64-16 2>/dev/null || true
    fi
}

start_docker_postgres() {
    echo "Starting PostgreSQL container via Docker Compose..."
    if docker info &>/dev/null; then
        (cd "${PROJECT_ROOT}" && docker compose up -d postgres)
        echo "Waiting for PostgreSQL container to become ready..."
        local retries=15
        while [ $retries -gt 0 ]; do
            if is_port_listening "localhost" 5432; then
                echo "[✓] PostgreSQL container is up and listening on port 5432."
                return 0
            fi
            sleep 1
            retries=$((retries - 1))
        done
        echo "[!] Container started, but port 5432 is not responding yet."
    else
        echo "Error: Docker daemon is not running. Please start Docker and try again." >&2
        return 1
    fi
}

install_docker() {
    echo "=========================================="
    echo " Installing Docker (${OS_TYPE})..."
    echo "=========================================="
    if [ "${OS_TYPE}" = "macOS" ]; then
        if command -v brew &>/dev/null; then
            brew install --cask docker
            echo "Please launch Docker Desktop from Applications to complete initialization, then re-run this script."
        else
            echo "Homebrew not found. Please install Docker Desktop from: https://www.docker.com/products/docker-desktop/"
        fi
    elif [ "${OS_TYPE}" = "Linux" ]; then
        echo "Running official Docker convenience script..."
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker "${USER}" || true
        sudo systemctl start docker || true
        sudo systemctl enable docker || true
        echo "Docker installed. Starting container..."
        start_docker_postgres
    elif [ "${OS_TYPE}" = "Windows" ]; then
        if command -v winget &>/dev/null; then
            winget install Docker.DockerDesktop
            echo "Please launch Docker Desktop to complete initialization, then re-run this script."
        else
            echo "Please download Docker Desktop from: https://www.docker.com/products/docker-desktop/"
        fi
    fi
}

install_native_postgres() {
    echo "=========================================="
    echo " Installing Native PostgreSQL (${OS_TYPE})..."
    echo "=========================================="
    if [ "${OS_TYPE}" = "macOS" ]; then
        if command -v brew &>/dev/null; then
            brew install postgresql@16
            brew services start postgresql@16
        else
            echo "Homebrew not found. Please install Homebrew or download PostgreSQL from: https://www.postgresql.org/download/"
        fi
    elif [ "${OS_TYPE}" = "Linux" ]; then
        if command -v apt-get &>/dev/null; then
            sudo apt-get update
            sudo apt-get install -y postgresql postgresql-contrib
            sudo systemctl start postgresql
            sudo systemctl enable postgresql
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y postgresql-server postgresql-contrib
            sudo postgresql-setup --initdb || true
            sudo systemctl start postgresql
            sudo systemctl enable postgresql
        elif command -v pacman &>/dev/null; then
            sudo pacman -S --noconfirm postgresql
            sudo -u postgres initdb -D /var/lib/postgres/data || true
            sudo systemctl start postgresql
            sudo systemctl enable postgresql
        else
            echo "Unknown package manager. Please install PostgreSQL manually from https://www.postgresql.org/download/"
        fi
    elif [ "${OS_TYPE}" = "Windows" ]; then
        if command -v winget &>/dev/null; then
            winget install PostgreSQL.PostgreSQL
            net start postgresql-x64-16 2>/dev/null || true
        else
            echo "Please download the PostgreSQL Windows installer from: https://www.postgresql.org/download/windows/"
        fi
    fi
}

# 1. Check if PostgreSQL is already active
if is_port_listening "localhost" 5432; then
    echo "[✓] PostgreSQL is already running and accessible on localhost:5432."
    exit 0
fi

# 2. Check if native PostgreSQL is installed but stopped
if command -v psql &>/dev/null || command -v postgres &>/dev/null || command -v pg_isready &>/dev/null; then
    echo "[!] PostgreSQL is installed locally but not currently active on port 5432."
    start_local_postgres

    if is_port_listening "localhost" 5432; then
        echo "[✓] Local PostgreSQL service successfully started on localhost:5432."
        exit 0
    else
        echo "[!] Tried starting local PostgreSQL service, but port 5432 is not responding yet."
    fi
fi

# 3. Check if Docker is installed
if command -v docker &>/dev/null; then
    echo "[✓] Docker is available on this machine."
    if docker info &>/dev/null; then
        start_docker_postgres
        exit 0
    else
        echo "[!] Docker daemon is not running. Please start Docker Desktop and run 'make db-up'."
        exit 1
    fi
fi

# 4. Neither is installed or running -> Prompt user for preferred installation method
CHOICE="${1:-}"

if [ -z "${CHOICE}" ]; then
    if [ -t 0 ]; then
        echo ""
        echo "Neither PostgreSQL nor Docker was detected as running on this machine."
        echo "Please select your preferred installation method:"
        echo "  1) Docker & Docker Compose (Recommended - Isolated container)"
        echo "  2) Native PostgreSQL service"
        echo "  3) Cancel"
        read -r -p "Enter choice [1-3] (default: 1): " USER_INPUT
        CHOICE="${USER_INPUT:-1}"
    else
        echo "[!] Non-interactive shell detected. Defaulting to Docker installation guidance."
        CHOICE="1"
    fi
fi

case "${CHOICE}" in
    1|--docker)
        install_docker
        ;;
    2|--native)
        install_native_postgres
        ;;
    3|--cancel)
        echo "Database setup cancelled."
        exit 0
        ;;
    *)
        echo "Invalid selection: ${CHOICE}" >&2
        exit 1
        ;;
esac

echo ""
echo "Database setup completed. You can apply schema migrations with:"
echo "  make upgrade"
