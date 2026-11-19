#!/usr/bin/env bash
# Qo'lda rollback:  bash deploy/rollback.sh [TAG]   (TAG berilmasa — .previous_tag)
set -euo pipefail
cd "$(dirname "$0")/.."
TARGET="${1:-$(cat .previous_tag 2>/dev/null || true)}"
[ -n "$TARGET" ] || { echo "✗ Qaytariladigan versiya topilmadi (.previous_tag yo'q)"; exit 1; }
REGISTRY="${REGISTRY:-$(docker inspect --format '{{.Config.Image}}' "$(docker compose ps -q web | head -1)" | sed 's|/web:.*||')}"
echo "Rollback → $TARGET  (registry: $REGISTRY)"
REGISTRY="$REGISTRY" bash deploy/deploy.sh "$TARGET"
