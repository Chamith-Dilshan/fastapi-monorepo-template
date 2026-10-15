#!/usr/bin/env bash
# Runs once per deploy, before the app starts (see the `prestart` service in
# docker-compose.yml). Migrations and the first-admin bootstrap happen
# here — never in the app's own startup, where N workers would race.
set -euo pipefail

alembic upgrade head
python -m app.initial_data
