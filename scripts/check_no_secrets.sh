#!/usr/bin/env bash
set -euo pipefail

PATTERNS='^(LINE_CHANNEL_ACCESS_TOKEN|LINE_CHANNEL_SECRET|OPENROUTER_API_KEY|DATABASE_URL|GOOGLE_SERVICE_ACCOUNT_JSON_PATH|GOOGLE_SHEET_ID)=.+'

if grep -RInE "$PATTERNS" . \
  --exclude-dir=.git \
  --exclude-dir=node_modules \
  --exclude-dir=.venv \
  --exclude-dir=docs \
  --exclude='*.example' \
  --exclude='*.sample' \
  --exclude='*.md' ; then
  echo "Possible secret found. Remove it before committing."
  exit 1
fi

echo "No obvious secrets found."
