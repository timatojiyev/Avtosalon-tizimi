#!/usr/bin/env bash
# Docker'siz ishga tushirish (SQLite bilan)
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements-dev.txt
python run_local.py
