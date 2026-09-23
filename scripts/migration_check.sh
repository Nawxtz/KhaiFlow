#!/usr/bin/env bash
set -euo pipefail

if [ -f backend/alembic.ini ]; then
  cd backend
  alembic upgrade head
  echo "Migration check passed."
else
  echo "No Alembic config yet; skipping migration check."
fi
