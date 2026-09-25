#!/bin/sh
# LayerToll single-container entrypoint for the Hugging Face Space.
# Starts MariaDB, Redis and RabbitMQ on 127.0.0.1, applies migrations, seeds the
# demo service, then the admin service, the agent gateway, the frontend and nginx.
# Internal passwords are random per boot and never printed.
set -eu

RUN=/tmp/layertoll
mkdir -p "$RUN/mysql" "$RUN/rabbitmq" "$RUN/logs"
rand() { python -c "import secrets;print(secrets.token_hex(16))"; }

export MYSQL_HOST=127.0.0.1 MYSQL_PORT=3306 MYSQL_USER=layertoll MYSQL_DB=layertoll
export MYSQL_PASSWORD="$(rand)"
export REDIS_HOST=127.0.0.1 REDIS_PORT=6379 REDIS_DB=0
export REDIS_PASSWORD="$(rand)"
export RABBITMQ_HOST=127.0.0.1 RABBITMQ_PORT=5672 RABBITMQ_USER=layertoll RABBITMQ_VHOST=/
export RABBITMQ_PASSWORD="$(rand)"
export PAYMENT_CONFIG_SECRET_KEY="$(python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")"
export DEBUG=false LOG_LEVEL=INFO ALLOWED_ORIGINS='*'
export AGENTPAY_API_INTERNAL_URL=http://127.0.0.1:8002
export DEMO_API_BASE_URL=http://127.0.0.1:8002/demo-api
# Hugging Face sets SPACE_HOST (e.g. user-layertoll.hf.space)
if [ -z "${AGENTPAY_PUBLIC_BASE_URL:-}" ]; then
  if [ -n "${SPACE_HOST:-}" ]; then export AGENTPAY_PUBLIC_BASE_URL="https://${SPACE_HOST}"; else export AGENTPAY_PUBLIC_BASE_URL="http://localhost:7860"; fi
fi

echo "[layertoll] starting MariaDB"
mariadb-install-db --datadir="$RUN/mysql" --user="$(whoami)" --auth-root-authentication-method=socket >/dev/null
mariadbd --datadir="$RUN/mysql" --socket="$RUN/mysqld.sock" --pid-file="$RUN/mysqld.pid" \
  --bind-address=127.0.0.1 --port=3306 --skip-log-bin --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci > "$RUN/logs/mariadb.log" 2>&1 &
for i in $(seq 1 60); do mariadb-admin --socket="$RUN/mysqld.sock" ping >/dev/null 2>&1 && break; sleep 1; done
mariadb --socket="$RUN/mysqld.sock" -uroot <<SQL
CREATE DATABASE IF NOT EXISTS layertoll CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'layertoll'@'127.0.0.1' IDENTIFIED BY '${MYSQL_PASSWORD}';
CREATE USER IF NOT EXISTS 'layertoll'@'localhost' IDENTIFIED BY '${MYSQL_PASSWORD}';
GRANT ALL PRIVILEGES ON layertoll.* TO 'layertoll'@'127.0.0.1';
GRANT ALL PRIVILEGES ON layertoll.* TO 'layertoll'@'localhost';
FLUSH PRIVILEGES;
SQL

echo "[layertoll] starting Redis"
redis-server --bind 127.0.0.1 --port 6379 --requirepass "$REDIS_PASSWORD" --save '' --appendonly no \
  --dir "$RUN" --daemonize yes --logfile "$RUN/logs/redis.log"

echo "[layertoll] starting RabbitMQ"
export HOME="$RUN/rabbitmq" RABBITMQ_MNESIA_BASE="$RUN/rabbitmq/mnesia" RABBITMQ_LOG_BASE="$RUN/logs" \
  RABBITMQ_NODENAME=rabbit@localhost RABBITMQ_NODE_IP_ADDRESS=127.0.0.1 RABBITMQ_DIST_PORT=25672 \
  RABBITMQ_ENABLED_PLUGINS_FILE="$RUN/rabbitmq/enabled_plugins" RABBITMQ_PID_FILE="$RUN/rabbitmq/rabbit.pid"
echo "[]." > "$RUN/rabbitmq/enabled_plugins"
RMQ=/usr/lib/rabbitmq/bin
"$RMQ/rabbitmq-server" -detached >/dev/null 2>&1
"$RMQ/rabbitmqctl" -q await_startup --timeout 120 >/dev/null
"$RMQ/rabbitmqctl" -q add_user "$RABBITMQ_USER" "$RABBITMQ_PASSWORD" >/dev/null
"$RMQ/rabbitmqctl" -q set_permissions -p / "$RABBITMQ_USER" '.*' '.*' '.*' >/dev/null
export HOME=/home/user

cd /app
echo "[layertoll] applying migrations"
python ./init_db.py > "$RUN/logs/init_db.log" 2>&1 || { tail -20 "$RUN/logs/init_db.log"; exit 1; }

# Admin console: password from the LAYERTOLL_ADMIN_PASSWORD Space secret, otherwise a
# random one nobody knows (the public demo does not need the console).
ADMIN_PW="${LAYERTOLL_ADMIN_PASSWORD:-$(rand)}"
ADMIN_MD5="$(python -c "import hashlib,sys;print(hashlib.md5(sys.argv[1].encode()).hexdigest())" "$ADMIN_PW")"
mariadb --socket="$RUN/mysqld.sock" -uroot layertoll -e "UPDATE \`user\` SET password='${ADMIN_MD5}' WHERE name='admin';"
unset ADMIN_PW ADMIN_MD5

echo "[layertoll] starting services"
uvicorn services.admin_service.main:app --host 127.0.0.1 --port 8001 > "$RUN/logs/admin_service.log" 2>&1 &
uvicorn services.api_service.main:app --host 127.0.0.1 --port 8002 > "$RUN/logs/api_service.log" 2>&1 &
(cd frontend && HOSTNAME=127.0.0.1 PORT=3000 node server.js > "$RUN/logs/frontend.log" 2>&1 &)
for i in $(seq 1 90); do curl -fsS http://127.0.0.1:8002/health >/dev/null 2>&1 && curl -fsS http://127.0.0.1:8001/ >/dev/null 2>&1 && break; sleep 1; done

python scripts/seed_demo.py || echo "[layertoll] demo seed failed (see logs)"

nginx -e /tmp/nginx-error.log -c /app/nginx.conf
echo "[layertoll] ready on :7860 — public base ${AGENTPAY_PUBLIC_BASE_URL}"
tail -F "$RUN/logs/admin_service.log" "$RUN/logs/api_service.log" "$RUN/logs/frontend.log"
