# LayerToll public demo image for a Hugging Face Docker Space (single container).
# Same app as scripts/Dockerfile, plus MariaDB, Redis and RabbitMQ running
# inside the container on 127.0.0.1 only. Runs as uid 1000 on port 7860
# (Hugging Face Spaces requirements). Data lives in /tmp and is re-seeded on
# every restart. Payments run in TEST MODE on X Layer testnet by default.

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
 && apt-get install -y --no-install-recommends nginx mariadb-server redis-server rabbitmq-server curl procps \
 && rm -rf /var/lib/apt/lists/* \
 && rm -f /etc/nginx/sites-enabled/default
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node

RUN useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/resource/init_db.py ./
COPY scripts/resource/sql ./sql
# MariaDB has no MySQL-8 utf8mb4_0900_ai_ci collation; use the equivalent it supports.
RUN sed -i 's/utf8mb4_0900_ai_ci/utf8mb4_unicode_ci/g' sql/*.sql
COPY pyproject.toml ./
COPY services ./services
COPY scripts/seed_demo.py ./scripts/seed_demo.py
COPY --from=frontend /out ./frontend
COPY deploy/huggingface/nginx.conf /app/nginx.conf
COPY deploy/huggingface/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && chown -R user:user /app

USER user
ENV HOME=/home/user \
    PYTHONUNBUFFERED=1 \
    AGENTPAY_NETWORK=xlayer-testnet \
    AGENTPAY_PAYMENT_MODE=test \
    AGENTPAY_VERIFY_ONCHAIN=false
EXPOSE 7860
CMD ["/app/entrypoint.sh"]
