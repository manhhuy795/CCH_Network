#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/logs/demo.pids"

if [ ! -f "$PID_FILE" ]; then
  echo "Khong thay $PID_FILE. Khong co process demo do start_demo.sh tao."
  exit 0
fi

while IFS=: read -r name pid; do
  [ -n "${pid:-}" ] || continue
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "Dung $name PID $pid"
    kill "$pid" >/dev/null 2>&1 || true
  fi
done < "$PID_FILE"

rm -f "$PID_FILE"
echo "Da dung cac process do start_demo.sh tao."
