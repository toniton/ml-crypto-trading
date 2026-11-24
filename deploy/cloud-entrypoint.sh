#!/usr/bin/env bash
set -euo pipefail

export TENANT_USER_ID="${TENANT_USER_ID:-default}"
echo "[cloud-entrypoint] Starting MCT container for tenant: ${TENANT_USER_ID}"

if [[ "${SKIP_MIGRATIONS:-false}" != "true" ]]; then
  echo "[cloud-entrypoint] Applying database migrations..."
  alembic upgrade head
fi

exec python main.py "$@"
