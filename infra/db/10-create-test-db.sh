#!/usr/bin/env bash
# Mounted into the dev database only (docker-compose.override.yml). Runs
# once, when the data volume is first created. The test suite needs its own
# database — it drops and recreates every table in it on each run — and
# this saves creating it by hand.
set -euo pipefail

if [ -n "${TEST_DB:-}" ]; then
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    -c "CREATE DATABASE \"$TEST_DB\""
fi
