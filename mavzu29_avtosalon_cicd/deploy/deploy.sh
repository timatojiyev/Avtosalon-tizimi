#!/usr/bin/env bash
# =====================================================================
#  Serverda deploy:  REGISTRY=ghcr.io/<owner>/avtosalon bash deploy/deploy.sh <TAG>
#
#  1) yangi image'larni tortadi  2) konteynerlarni yangilaydi (bazalar va volume'lar saqlanadi)
#  3) health check + read-only smoke test  4) muvaffaqiyatsiz bo'lsa — oldingi versiyaga AVTOMATIK qaytaradi
#  Holat fayllari: .current_tag, .previous_tag, deploy-history.log
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${1:?Foydalanish: deploy.sh <TAG>}"
export TAG REGISTRY="${REGISTRY:?REGISTRY o'rnatilmagan}"
export GATEWAY_PORT="${GATEWAY_PORT:-8080}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml -f deploy/docker-compose.deploy.yml)
[ -f .env ] || { echo "✗ .env topilmadi (DB parollari). .env.example asosida yarating."; exit 1; }

PREV="$(cat .current_tag 2>/dev/null || true)"
log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a deploy-history.log; }

log "DEPLOY boshlandi: ${PREV:-<yo'q>} → $TAG"
"${COMPOSE[@]}" pull --quiet
"${COMPOSE[@]}" up -d --no-build --remove-orphans

if scripts/wait-healthy.sh 180 && SMOKE_READONLY=1 scripts/smoke-test.sh "http://localhost:${GATEWAY_PORT}"; then
  [ -n "$PREV" ] && [ "$PREV" != "$TAG" ] && echo "$PREV" > .previous_tag
  echo "$TAG" > .current_tag
  docker image prune -f --filter "until=168h" >/dev/null || true
  log "DEPLOY muvaffaqiyatli: $TAG ✓"
else
  log "DEPLOY muvaffaqiyatsiz: $TAG ✗"
  "${COMPOSE[@]}" logs --no-color --tail=80 || true
  if [ -n "$PREV" ]; then
    log "Avtomatik rollback → $PREV"
    TAG="$PREV" "${COMPOSE[@]}" up -d --no-build --remove-orphans
    TAG="$PREV" scripts/wait-healthy.sh 180 && log "ROLLBACK muvaffaqiyatli: $PREV" || log "ROLLBACK ham muvaffaqiyatsiz — qo'lda aralashuv kerak!"
  fi
  exit 1
fi
