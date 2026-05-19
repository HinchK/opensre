#!/usr/bin/env bash
# infra/scripts/signoz/env.sh
# Source this file to export the minimum SigNoz env vars for OpenSRE.

export SIGNOZ_URL="${SIGNOZ_URL:-http://localhost:3301}"
export SIGNOZ_API_KEY="${SIGNOZ_API_KEY:-}"

# Optional ClickHouse fallback (still used for logs/traces in the current integration).
export SIGNOZ_CLICKHOUSE_HOST="${SIGNOZ_CLICKHOUSE_HOST:-localhost}"
export SIGNOZ_CLICKHOUSE_PORT="${SIGNOZ_CLICKHOUSE_PORT:-8123}"
export SIGNOZ_CLICKHOUSE_USER="${SIGNOZ_CLICKHOUSE_USER:-default}"
export SIGNOZ_CLICKHOUSE_PASSWORD="${SIGNOZ_CLICKHOUSE_PASSWORD:-}"
export SIGNOZ_CLICKHOUSE_DATABASE="${SIGNOZ_CLICKHOUSE_DATABASE:-default}"

echo "SigNoz environment configured:"
echo "  SIGNOZ_CLICKHOUSE_HOST=$SIGNOZ_CLICKHOUSE_HOST"
echo "  SIGNOZ_CLICKHOUSE_PORT=$SIGNOZ_CLICKHOUSE_PORT"
echo "  SIGNOZ_CLICKHOUSE_USER=$SIGNOZ_CLICKHOUSE_USER"
echo "  SIGNOZ_CLICKHOUSE_DATABASE=$SIGNOZ_CLICKHOUSE_DATABASE"
echo "  SIGNOZ_URL=$SIGNOZ_URL"
echo "  SIGNOZ_API_KEY=${SIGNOZ_API_KEY:+***set***}"
