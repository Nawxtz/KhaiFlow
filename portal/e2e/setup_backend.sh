#!/usr/bin/env bash
# Prepare a disposable database for Playwright: migrations, demo data and test accounts.
# Needs DATABASE_URL. Never point this at a real database.
set -euo pipefail
cd "$(dirname "$0")/../../backend"
alembic upgrade head
python - <<'PY'
import seed_demo
from app.auth.service import create_user
from app.core.database import SessionLocal

seed_demo.seed_demo_data()
with SessionLocal() as db:
    create_user(db, "owner", "e2e-only-test-password", "owner")
    create_user(db, "staff", "e2e-only-test-password", "staff")
PY
