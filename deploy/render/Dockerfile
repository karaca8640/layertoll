# LayerToll public demo on a free Render web service (512 MB, one container).
# Lite mode: SQLite + in-memory Redis, no RabbitMQ, admin + gateway in one
# Python process. TEST MODE payments on X Layer testnet. Data lives in /tmp and
# is re-seeded on every start (free instances sleep and restart).

FROM node:22-bookworm-slim AS frontend
WORKDIR /build
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm install -g pnpm@10
COPY frontend/package.json ./
RUN pnpm install --no-frozen-lockfile
COPY frontend/ ./
RUN pnpm build \
 && mkdir -p /out/.next \
 && cp -R .next/standalone/. /out/ \
 && cp -R .next/static /out/.next/ \
 && cp -R public /out/

FROM python:3.12-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends nginx curl \
 && rm -rf /var/lib/apt/lists/* \
 && rm -f /etc/nginx/sites-enabled/default
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node

WORKDIR /app
COPY requirements.txt requirements-lite.txt ./
RUN pip install --no-cache-dir -r requirements-lite.txt
COPY pyproject.toml ./
COPY services ./services
COPY scripts/seed_demo.py ./scripts/seed_demo.py
COPY --from=frontend /out ./frontend
COPY deploy/render/nginx.conf.template /app/nginx.conf.template
COPY deploy/render/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    LAYERTOLL_LITE=true \
    DATABASE_URL=sqlite:////tmp/layertoll.db \
    AGENTPAY_NETWORK=xlayer-testnet \
    AGENTPAY_PAYMENT_MODE=test \
    AGENTPAY_VERIFY_ONCHAIN=false \
    AGENTPAY_API_INTERNAL_URL=http://127.0.0.1:8001 \
    DEMO_API_BASE_URL=http://127.0.0.1:8001/demo-api \
    ALLOWED_ORIGINS=* \
    PORT=10000
EXPOSE 10000
CMD ["/app/entrypoint.sh"]
