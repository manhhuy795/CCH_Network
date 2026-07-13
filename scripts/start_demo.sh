#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/demo.pids"
BACKEND_DIR="$ROOT_DIR/dashboard/backend"
FRONTEND_DIR="$ROOT_DIR/dashboard/frontend"
BACKEND_VENV="$BACKEND_DIR/.venv"
INSTALL_DEPS=0

if [[ "${1:-}" == "--install" ]]; then
  INSTALL_DEPS=1
fi

mkdir -p "$LOG_DIR"

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Thieu dependency he thong: $1"
    echo "Cai goi co ban:"
    echo "  sudo apt update"
    echo "  sudo apt install -y python3 python3-venv python3-pip nodejs npm curl"
    exit 1
  fi
}

port_open() {
  timeout 1 bash -c "cat < /dev/null > /dev/tcp/127.0.0.1/$1" >/dev/null 2>&1
}

wait_port() {
  local name="$1"
  local port="$2"
  local log_file="$3"
  for _ in {1..30}; do
    if port_open "$port"; then
      echo "OK   $name da san sang tren port $port"
      return 0
    fi
    sleep 1
  done
  echo "FAIL $name khong mo port $port. Log cuoi:"
  tail -n 80 "$log_file" 2>/dev/null || true
  return 1
}

need_cmd python3
need_cmd npm

if [[ -f "$PID_FILE" ]]; then
  echo "Da co PID file: $PID_FILE"
  echo "Neu muon khoi dong lai, chay truoc:"
  echo "  ./scripts/stop_demo.sh"
  exit 1
fi

if [[ "$INSTALL_DEPS" -eq 1 ]]; then
  echo "Cai/cap nhat dependency dashboard theo yeu cau --install..."
  python3 -m venv "$BACKEND_VENV"
  "$BACKEND_VENV/bin/python" -m pip install --upgrade pip wheel
  "$BACKEND_VENV/bin/python" -m pip install -r "$BACKEND_DIR/requirements.txt"
  (cd "$FRONTEND_DIR" && npm install)
fi

if [[ ! -x "$ROOT_DIR/sdn_mpls_demo/run_controller.sh" ]]; then
  echo "Thieu quyen execute. Chay:"
  echo "  chmod +x sdn_mpls_demo/*.sh scripts/*.sh"
  exit 1
fi

if [[ ! -x "$BACKEND_VENV/bin/python" ]]; then
  echo "Chua co Python venv cho backend: $BACKEND_VENV"
  echo "Chay lan dau:"
  echo "  ./scripts/start_demo.sh --install"
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Chua co node_modules cho React frontend."
  echo "Chay lan dau:"
  echo "  ./scripts/start_demo.sh --install"
  exit 1
fi

: > "$PID_FILE"

if port_open 6653; then
  echo "Controller port 6653 da co san, khong khoi dong them controller."
else
  echo "Khoi dong OS-Ken Controller..."
  "$ROOT_DIR/sdn_mpls_demo/run_controller.sh" > "$LOG_DIR/controller.log" 2>&1 &
  echo "controller:$!" >> "$PID_FILE"
fi

if port_open 8000; then
  echo "Backend port 8000 da co san, khong khoi dong them backend."
else
  echo "Khoi dong FastAPI backend..."
  (
    cd "$BACKEND_DIR"
    "$BACKEND_VENV/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
  ) > "$LOG_DIR/backend.log" 2>&1 &
  echo "backend:$!" >> "$PID_FILE"
fi

if port_open 5173; then
  echo "Frontend port 5173 da co san, khong khoi dong them frontend."
else
  echo "Khoi dong React frontend..."
  (
    cd "$FRONTEND_DIR"
    npm run dev -- --host 0.0.0.0 --port 5173
  ) > "$LOG_DIR/frontend.log" 2>&1 &
  echo "frontend:$!" >> "$PID_FILE"
fi

wait_port "Backend" 8000 "$LOG_DIR/backend.log"
wait_port "Frontend" 5173 "$LOG_DIR/frontend.log"

VM_IPS="$(hostname -I 2>/dev/null | xargs || true)"

echo
echo "Da khoi dong dashboard."
echo "Mo trong Ubuntu VM:"
echo "  Dashboard: http://127.0.0.1:5173"
echo "  Backend:   http://127.0.0.1:8000"
echo "  API Docs:  http://127.0.0.1:8000/docs"
if [[ -n "$VM_IPS" ]]; then
  echo
  echo "Mo tu Windows host, dung mot trong cac IP VM sau thay cho <IP_VM>:"
  for ip in $VM_IPS; do
    echo "  http://$ip:5173"
  done
fi
echo
echo "Log:"
echo "  tail -n 80 logs/backend.log"
echo "  tail -n 80 logs/frontend.log"
