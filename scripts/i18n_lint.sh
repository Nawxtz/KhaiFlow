#!/usr/bin/env bash
set -euo pipefail

TARGETS=()

if [ -d backend/app ]; then
  TARGETS+=("backend/app")
fi

if [ -d portal/app ]; then
  TARGETS+=("portal/app")
fi

if [ ${#TARGETS[@]} -eq 0 ]; then
  echo "No app directories yet; skipping i18n lint."
  exit 0
fi

if command -v rg >/dev/null 2>&1; then
  if rg -n "[\u0E00-\u0E7F]" "${TARGETS[@]}" \
    -g '!**/locale/**' \
    -g '!**/locales/**' \
    -g '!**/*.json'; then
    echo "Thai strings found outside locale directories."
    exit 1
  fi
else
  echo "ripgrep not installed; skipping advanced i18n lint."
fi

echo "i18n lint passed."
