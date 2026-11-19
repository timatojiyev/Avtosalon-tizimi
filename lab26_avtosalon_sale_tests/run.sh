#!/usr/bin/env bash
# Linux / macOS uchun bir martalik o'rnatish va ishga tushirish
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "[1/3] Virtual muhit yaratilmoqda..."
  python3 -m venv .venv
fi
source .venv/bin/activate
echo "[2/3] Paketlar o'rnatilmoqda..."
pip install --upgrade pip >/dev/null
pip install -r requirements-test.txt
echo "[3/3] Dastur ishga tushmoqda..."
python run.py
