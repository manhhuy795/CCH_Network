#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/demo.pids"
mkdir -p "$LOG_DIR"
: > "$PID_FILE"

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Thieu dependency: $1"
    exit 1
  fi
}

need_cmd python3
need_cmd npm

if [ ! -x "$ROOT_DIR/sdn_mpls_demo/run_controller.sh" ]; then
  echo "Thieu quyen execute. Chay: chmod +x sdn_mpls_demo/*.sh scripts/*.sh"
  exit 1
fi

echo "Khoi dong OS-Ken Controller..."
"$ROOT_DIR/sdn_mpls_demo/run_controller.sh" > "$LOG_DIR/controller.log" 2>&1 &
echo "controller:$!" >> "$PID_FILE"

echo "Khoi dong FastAPI backend..."
(
  cd "$ROOT_DIR"
  python3 -m uvicorn dashboard.backend.app.main:app --host 0.0.0.0 --port 8000
) > "$LOG_DIR/backend.log" 2>&1 &
echo "backend:$!" >> "$PID_FILE"

echo "Khoi dong React frontend..."
(
  cd "$ROOT_DIR/dashboard/frontend"
  npm run dev -- --host 0.0.0.0 --port 5173
) > "$LOG_DIR/frontend.log" 2>&1 &
echo "frontend:$!" >> "$PID_FILE"

echo
echo "Controller: 127.0.0.1:6653"
echo "Backend:    http://localhost:8000"
echo "API Docs:   http://localhost:8000/docs"
echo "Dashboard:  http://localhost:5173"
echo "PID file:   $PID_FILE"
echo
echo "Neu truy cap tu may host: http://<IP_VM>:5173"
