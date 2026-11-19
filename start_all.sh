#!/usr/bin/env bash
# 26–30-ishlarni BITTA buyruq bilan ishga tushiradi:   bash start_all.sh
# To'xtatish:                                         bash stop_all.sh
cd "$(dirname "$0")" || exit 1
mkdir -p logs

if [ -s logs/pids ]; then
  echo "Avvalgi nusxa to'xtatilmoqda..."
  bash stop_all.sh >/dev/null 2>&1
fi
: > logs/pids

command -v python3 >/dev/null || { echo "✗ python3 topilmadi:  sudo apt install python3 python3-venv"; exit 1; }
python3 -c "import ensurepip" 2>/dev/null || { echo "✗ python3-venv kerak:  sudo apt install python3-venv"; exit 1; }

port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# papka | skript | asosiy port | qo'shimcha portlar
PROJECTS=(
  "lab26_avtosalon_sale_tests|run.sh|5026|"
  "lab27_avtosalon_docker_compose|run_local.sh|8270|8271 8272 8273 8274"
  "mavzu28_avtosalon_multiservice|run_local.sh|8280|8281 8282 8283 8284 8285"
  "mavzu29_avtosalon_cicd|run_local.sh|8290|8291 8292 8293 8294 8295"
  "mavzu30_yakuniy_loyiha|run_local.sh|8300|8301 8302 8303 8304 8305"
)

for item in "${PROJECTS[@]}"; do
  IFS='|' read -r dir script port extra <<< "$item"
  busy=""
  for p in $port $extra; do port_busy "$p" && busy="$busy $p"; done
  if [ -n "$busy" ]; then
    echo "  ⚠ $dir o'tkazib yuborildi — port(lar) band:$busy   (tekshirish: sudo ss -ltnp | grep :$port)"
    continue
  fi
  # setsid — har bir loyiha o'z jarayonlar guruhida; stop_all.sh butun guruhni to'xtatadi
  setsid bash -c "cd '$dir' && exec bash '$script'" > "logs/$dir.log" 2>&1 < /dev/null &
  echo "$! $dir $port" >> logs/pids
  echo "  → $dir  (http://127.0.0.1:$port, log: logs/$dir.log)"
done

echo
echo "Paketlar o'rnatilmoqda va servislar ko'tarilmoqda (birinchi marta 1–3 daqiqa)..."
for i in $(seq 1 180); do
  up=0; total=0
  while read -r pid dir port; do
    total=$((total + 1))
    port_busy "$port" && up=$((up + 1))
  done < logs/pids
  printf "\r  Tayyor: %d / %d  " "$up" "$total"
  [ "$up" -eq "$total" ] && break
  sleep 1
done
echo

while read -r pid dir port; do
  if port_busy "$port"; then echo "  ✓ $dir  →  http://127.0.0.1:$port"
  else echo "  ✗ $dir ishga tushmadi — xatoni ko'ring:  tail -n 30 logs/$dir.log"; fi
done < logs/pids

for b in firefox google-chrome google-chrome-stable chromium chromium-browser; do
  if command -v "$b" >/dev/null; then "$b" "$(pwd)/index.html" >/dev/null 2>&1 & break; fi
done
echo
echo "Panel (barcha topshiriqlar ro'yxati): $(pwd)/index.html"
echo "Yakuniy loyiha: http://127.0.0.1:8300   login: admin / admin123"
echo "To'xtatish:     bash stop_all.sh"
