#!/usr/bin/env bash
# Gateway orqali tizimning asosiy oqimini tekshiradi.  Foydalanish: scripts/smoke-test.sh [http://localhost:8080]
set -euo pipefail
BASE=${1:-http://localhost:8080}
ok() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; exit 1; }
KEY=${GATEWAY_API_KEY:-dev-api-key-change-me}
api() { curl -fsS -H "X-API-Key: $KEY" "$@"; }
json() { python3 -c "import json,sys; print(json.load(sys.stdin)$1)"; }

echo "Smoke test: $BASE"
curl -fsS "$BASE/gateway/health" >/dev/null && ok "gateway" || fail "gateway"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/cars")" = "401" ] && ok "kalitsiz /api → 401" || fail "API kalitsiz ochiq!"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/")" = "302" ] && ok "panel → login sahifasiga yo'naltiradi" || fail "panel loginsiz ochiq!"
for s in car customer sales financing; do
  api "$BASE/api/health/$s-service" | grep -q '"ok"' && ok "$s-service /health" || fail "$s-service"
done
api "$BASE/api/notifications" >/dev/null && ok "notification-worker /notifications" || fail "notification-worker"
if [ "${SMOKE_READONLY:-0}" = "1" ]; then
  api "$BASE/api/cars" >/dev/null && ok "GET /api/cars (read-only rejim — production ma'lumotlari o'zgartirilmaydi)"
  echo "Hammasi joyida ✓"; exit 0
fi
CAR=$(api "$BASE/api/cars?status=sotuvda" | json "[0]['id']") || fail "mashina topilmadi"
SALE=$(api -X POST "$BASE/api/sales" -H 'Content-Type: application/json' \
       -d "{\"car_id\": $CAR, \"customer_id\": 1, \"payment_method\": \"naqd\"}")
SID=$(echo "$SALE" | json "['id']"); PRICE=$(echo "$SALE" | json "['price']")
ok "sotuv yaratildi #$SID"
api -X POST "$BASE/api/sales/$SID/complete" -H 'Content-Type: application/json' -d "{\"paid\": $PRICE}" \
  | grep -q yakunlangan && ok "sotuv yakunlandi" || fail "yakunlash"
[ "$(api "$BASE/api/cars/$CAR" | json "['status']")" = "sotilgan" ] && ok "avtomobil holati: sotilgan" || fail "car status"
sleep 2
api "$BASE/api/notifications" | grep -q "sale.completed" && ok "notification-worker hodisani oldi" || fail "hodisa yetib kelmadi"
echo "Hammasi joyida ✓"
