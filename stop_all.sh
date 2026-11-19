#!/usr/bin/env bash
# start_all.sh ishga tushirgan barcha loyihalarni to'xtatadi.
cd "$(dirname "$0")" || exit 1
if [ ! -s logs/pids ]; then echo "Ishlab turgan loyiha yo'q (logs/pids bo'sh)."; exit 0; fi
while read -r pid dir port; do
  if kill -- "-$pid" 2>/dev/null; then echo "  ■ $dir to'xtatildi"; else echo "  · $dir allaqachon to'xtagan"; fi
done < logs/pids
sleep 1
while read -r pid dir port; do kill -9 -- "-$pid" 2>/dev/null; done < logs/pids
: > logs/pids
echo "Tayyor."
