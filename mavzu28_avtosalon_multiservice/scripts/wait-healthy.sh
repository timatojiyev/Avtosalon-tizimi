#!/usr/bin/env bash
# Barcha konteynerlar "healthy" bo'lguncha kutadi (CI va deploy uchun).  Foydalanish: scripts/wait-healthy.sh [timeout_s]
set -euo pipefail
TIMEOUT=${1:-180}; START=$(date +%s)
while true; do
  STATUS=$(docker compose ps --format '{{.Service}} {{.Health}}' | grep -v ' healthy$' | grep -v ' $' || true)
  if [ -z "$STATUS" ]; then echo "✓ Barcha servislar sog'lom"; exit 0; fi
  if [ $(( $(date +%s) - START )) -gt "$TIMEOUT" ]; then
    echo "✗ ${TIMEOUT}s ichida sog'lom bo'lmadi:"; echo "$STATUS"; docker compose ps; exit 1
  fi
  sleep 3
done
