#!/usr/bin/env bash
set -euo pipefail

FILES=("parser.py" "geo_engine.py" "constants.py" "models.py")
status=0

for f in "${FILES[@]}"; do
  if [ ! -e "$f" ] && [ ! -e "backend/$f" ]; then
    continue
  fi
  if ! cmp -s "$f" "backend/$f"; then
    echo "$f differs from backend/$f"
    status=1
  fi
done

exit "$status"
