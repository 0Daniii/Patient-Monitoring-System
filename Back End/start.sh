#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# start.sh – Multi-service launcher for BackendAppPMB
# -----------------------------------------------------------------------------

# 1) Compute where this script lives
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "→ BASE_DIR is $BASE_DIR"

# 2) Postgres data dir & port
PGDATA="$BASE_DIR/pgdata"
PGPORT=5433

# 3) Initialize Postgres data directory if missing
if [ ! -f "$PGDATA/PG_VERSION" ]; then
  echo "→ Initializing PostgreSQL data directory at $PGDATA"
  mkdir -p "$PGDATA"
  initdb -D "$PGDATA"
fi

# 4) Start or skip Postgres on PGPORT
echo "→ Checking PostgreSQL on port $PGPORT..."
if pg_isready -h localhost -p "$PGPORT" &>/dev/null; then
  echo "→ PostgreSQL already running on port $PGPORT; skipping start."
else
  echo "→ Starting PostgreSQL on port $PGPORT..."
  pg_ctl -D "$PGDATA" \
         -l "$PGDATA/logfile" \
         -o "-c listen_addresses='*' -c port=$PGPORT" \
         start
fi

# 5) Start or skip Mosquitto on 1883
echo "→ Checking MQTT port 1883..."
if lsof -i TCP:1883 >/dev/null 2>&1; then
  echo "→ Port 1883 already in use; skipping Mosquitto start."
else
  echo "→ Starting Mosquitto MQTT broker..."
  mosquitto &
fi

# 6) Wait for Postgres to be ready
echo "→ Waiting for PostgreSQL to be ready on port ${PGPORT}…"
until pg_isready -h localhost -p "$PGPORT" &>/dev/null; do
  sleep 1
done
echo "→ PostgreSQL is up!"

# 7) Launch the Flask app
echo "→ Launching Flask app (BackendAppPMB.py)…"
cd "$BASE_DIR"

export FLASK_ENV=production        # or "development"
export PGPORT="$PGPORT"
export DATABASE_URL="postgresql://admin:adminPassword@localhost:${PGPORT}/v3db"

# Replace exec here so this script hands over to Python process
exec python3 "/Users/len/Downloads/Patient-Monitoring-Blockchain-main3/Back End/BackendAppPMB.py"

