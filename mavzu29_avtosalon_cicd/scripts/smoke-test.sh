#!/usr/bin/env bash
# Gateway orqali tizimning asosiy oqimini tekshiradi.  Foydalanish: scripts/smoke-test.sh [http://localhost:8080]
set -euo pipefail
BASE=${1:-http://localhost:8080}
ok() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; exit 1; }
json() { python3 -c "import json,sys; print(json.load(sys.stdin)$1)"; }

echo "Smoke test: $BASE"
curl -fsS "$BASE/gateway/health" >/dev/null && ok "gateway" || fail "gateway"
for s in car customer sales financing; do
  curl -fsS "$BASE/api/health/$s-service" | grep -q '"ok"' && ok "$s-service /health" || fail "$s-service"
done
curl -fsS "$BASE/api/notifications" >/dev/null && ok "notification-worker /notifications" || fail "notification-worker"
if [ "${SMOKE_READONLY:-0}" = "1" ]; then
  curl -fsS "$BASE/api/cars" >/dev/null && ok "GET /api/cars (read-only rejim — production ma'lumotlari o'zgartirilmaydi)"
  echo "Hammasi joyida ✓"; exit 0
fi
CAR=$(curl -fsS "$BASE/api/cars?status=sotuvda" | json "[0]['id']") || fail "mashina topilmadi"
SALE=$(curl -fsS -X POST "$BASE/api/sales" -H 'Content-Type: application/json' \
       -d "{\"car_id\": $CAR, \"customer_id\": 1, \"payment_method\": \"naqd\"}")
SID=$(echo "$SALE" | json "['id']"); PRICE=$(echo "$SALE" | json "['price']")
ok "sotuv yaratildi #$SID"
curl -fsS -X POST "$BASE/api/sales/$SID/complete" -H 'Content-Type: application/json' -d "{\"paid\": $PRICE}" \
  | grep -q yakunlangan && ok "sotuv yakunlandi" || fail "yakunlash"
[ "$(curl -fsS "$BASE/api/cars/$CAR" | json "['status']")" = "sotilgan" ] && ok "avtomobil holati: sotilgan" || fail "car status"
sleep 2
curl -fsS "$BASE/api/notifications" | grep -q "sale.completed" && ok "notification-worker hodisani oldi" || fail "hodisa yetib kelmadi"
echo "Hammasi joyida ✓"
