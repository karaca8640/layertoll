#!/bin/sh
# LayerToll lite entrypoint (Render free web service or any single container).
set -eu
LOG=/tmp/layertoll-logs
mkdir -p "$LOG"

# Public origin: explicit setting, else Render's RENDER_EXTERNAL_URL, else localhost.
if [ -z "${AGENTPAY_PUBLIC_BASE_URL:-}" ]; then
  export AGENTPAY_PUBLIC_BASE_URL="${RENDER_EXTERNAL_URL:-http://localhost:${PORT}}"
fi
export PAYMENT_CONFIG_SECRET_KEY="${PAYMENT_CONFIG_SECRET_KEY:-$(python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")}"

cd /app
python -m services.lite.bootstrap
python scripts/seed_demo.py || echo "[layertoll] demo seed failed"

uvicorn services.lite.app:app --host 127.0.0.1 --port 8001 --timeout-graceful-shutdown 2 > "$LOG/app.log" 2>&1 &
(cd frontend && HOSTNAME=127.0.0.1 PORT=3000 node server.js > "$LOG/frontend.log" 2>&1 &)

sed "s/__PORT__/${PORT}/" /app/nginx.conf.template > /tmp/nginx.conf
for i in $(seq 1 120); do curl -fsS http://127.0.0.1:8001/health >/dev/null 2>&1 && break; sleep 1; done
nginx -e /tmp/nginx-error.log -c /tmp/nginx.conf
echo "[layertoll] ready on :${PORT} — public base ${AGENTPAY_PUBLIC_BASE_URL} (TEST MODE, ${AGENTPAY_NETWORK})"
tail -F "$LOG/app.log" "$LOG/frontend.log"
