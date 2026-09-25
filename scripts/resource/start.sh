#!/bin/sh
# LayerToll container entrypoint (modified from the upstream XPack start.sh, Apache-2.0).
# Configuration comes from environment variables (docker compose env_file); no .env is copied.
set -e

LOG_DIR="$(pwd)/logs"
mkdir -p "${LOG_DIR}"

# Wait for MySQL, then apply versioned migrations (init.sql + version-*.sql).
# Never start the services on top of a failed migration.
migrated=0
for i in $(seq 1 20); do
    if python ./init_db.py; then
        migrated=1
        break
    fi
    echo "Database init/migration failed (attempt $i), retrying in 3s..."
    sleep 3
done
if [ "$migrated" != "1" ]; then
    echo "Database migration failed; refusing to start." >&2
    exit 1
fi

nohup uvicorn services.admin_service.main:app --host 0.0.0.0 --port 8001 --timeout-graceful-shutdown 2 > "${LOG_DIR}/admin_service.log" 2>&1 &
nohup uvicorn services.api_service.main:app --host 0.0.0.0 --port 8002 --timeout-graceful-shutdown 2 > "${LOG_DIR}/api_service.log" 2>&1 &
(cd frontend && HOSTNAME=127.0.0.1 PORT=3000 nohup node server.js > "${LOG_DIR}/frontend.log" 2>&1 &)

sleep 2
nginx

tail -F "${LOG_DIR}"/*.log
