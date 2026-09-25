# LayerToll all-in-one image: nginx + Next.js frontend + admin service + agent gateway.
# Based on the upstream XPack Dockerfile (Apache-2.0); modified to build the
# frontend in-image and to use Debian (wheels for the web3/x402 stack).

# ---------- frontend build ----------
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

# ---------- runtime ----------
FROM python:3.12-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends nginx curl \
 && rm -rf /var/lib/apt/lists/* \
 && rm -f /etc/nginx/sites-enabled/default
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/resource/default.conf /etc/nginx/conf.d/default.conf
COPY scripts/resource/start.sh scripts/resource/init_db.py ./
COPY scripts/resource/sql ./sql
COPY pyproject.toml ./
COPY services ./services
COPY --from=frontend /out ./frontend

EXPOSE 80
HEALTHCHECK --interval=20s --timeout=5s --start-period=60s CMD curl -fsS http://127.0.0.1:8002/health || exit 1
CMD ["sh", "./start.sh"]
