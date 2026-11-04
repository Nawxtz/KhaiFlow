#!/usr/bin/env bash
set -euo pipefail
# Fails when a secret value is committed. Three shapes (P-001; a LINE secret assigned in a .py file slipped through
# the first, env-only pattern in 2026-10):
#   1. env lines: NAME=value
#   2. code: NAME = "value" / NAME: 'value' (16+ chars)
#   3. known token shapes in any file
NAMES='LINE_CHANNEL_ACCESS_TOKEN|LINE_CHANNEL_SECRET|OPENROUTER_API_KEY|DATABASE_URL|GOOGLE_SERVICE_ACCOUNT_JSON_PATH|GOOGLE_SHEET_ID|PAYMENT_QR_SECRET|GATEWAY_WEBHOOK_SECRET'
PATTERNS="^($NAMES)=.+|($NAMES)[\"']?[[:space:]]*[:=][[:space:]]*[\"'][^\"'[:space:]]{16,}[\"']|sk-or-v1-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"

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
