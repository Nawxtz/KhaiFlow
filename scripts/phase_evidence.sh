#!/usr/bin/env bash
set -euo pipefail

PHASE="${1:-}"

if [ -z "$PHASE" ]; then
  echo "Usage: $0 <phase-number>"
  exit 1
fi

mkdir -p phase-evidence
FILE="phase-evidence/phase-${PHASE}-evidence.md"

cat > "$FILE" <<TEMPLATE
# Phase ${PHASE} Evidence

Phase: ${PHASE}
Status: READY_FOR_REVIEW
Date:

## Commands run

- make lint
- make typecheck
- make test
- make build
- make secret-scan
- make migration-check
- make i18n-lint

## Test summary

- Backend:
- Portal:
- Concurrency:
- Security:

## Acceptance criteria mapping

| Criterion | Test | Result |
|---|---|---|
|  |  |  |

## Files changed

- 

## Migrations

- 

## Assumptions

- 

## Protected files touched

- none / list with reason

## Payment/security impact

- none / describe

## PDPA impact

- none / describe

## Manual verification steps

1. 

## Remaining risks

- 
TEMPLATE

echo "Created ${FILE}"
