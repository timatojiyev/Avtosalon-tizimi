#!/usr/bin/env bash
# CI bosqichlarini lokal kompyuterda ketma-ket bajaradi (push qilishdan oldin tekshirish uchun).
set -euo pipefail
cd "$(dirname "$0")/.."
step() { echo; echo "━━━ $1 ━━━"; }
step "1/4 Lint (ruff)";            ruff check .
step "2/4 Compose konfiguratsiya"; docker compose -f docker-compose.yml config --quiet && docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet && echo ok
step "3/4 Testlar + coverage";     pytest tests -q --cov=libs --cov=services --cov=web --cov-report=term --cov-fail-under=75
if [ "${SKIP_DOCKER:-0}" != "1" ]; then
  step "4/4 Integratsiya (docker)"
  export TAG=local-ci GIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo local) BUILD_DATE=$(date -u +%FT%TZ)
  docker compose -f docker-compose.yml up -d --build
  trap 'docker compose -f docker-compose.yml down -v' EXIT
  scripts/wait-healthy.sh 240 && scripts/smoke-test.sh http://localhost:${GATEWAY_PORT:-8080}
fi
echo; echo "✓ CI lokal muvaffaqiyatli"
