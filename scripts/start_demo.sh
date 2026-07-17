#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/demo.pids"
OPERATOR_TOKEN_FILE="$LOG_DIR/operator.token"
BACKEND_DIR="$ROOT_DIR/dashboard/backend"
FRONTEND_DIR="$ROOT_DIR/dashboard/frontend"
BACKEND_VENV="$BACKEND_DIR/.venv"
INSTALL_DEPS=0
STARTUP_COMPLETE=0
BACKEND_PRIVILEGE_PREFIX=()

if [[ "${1:-}" == "--install" ]]; then
  INSTALL_DEPS=1
fi

mkdir -p "$LOG_DIR"

cleanup_failed_start() {
  if [[ "$STARTUP_COMPLETE" -eq 1 || ! -f "$PID_FILE" ]]; then
    return
  fi
  echo "Startup khong hoan tat. Dang dung cac process vua tao..."
  while IFS=: read -r _name pid; do
    [[ -n "${pid:-}" ]] || continue
    kill "$pid" >/dev/null 2>&1 || true
  done < "$PID_FILE"
  rm -f "$PID_FILE"
}

trap cleanup_failed_start EXIT

if [[ -z "${CCH_DASHBOARD_OPERATOR_TOKEN:-}" ]]; then
  if [[ ! -s "$OPERATOR_TOKEN_FILE" ]]; then
    python3 - <<'PY' > "$OPERATOR_TOKEN_FILE"
import secrets
print(secrets.token_urlsafe(24))
PY
    chmod 600 "$OPERATOR_TOKEN_FILE"
  fi
  export CCH_DASHBOARD_OPERATOR_TOKEN="$(cat "$OPERATOR_TOKEN_FILE")"
fi

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
  local pid="${4:-}"
  for _ in {1..30}; do
    if ! pid_alive "$pid"; then
      echo "FAIL $name process da dung. Log cuoi:"
      tail -n 80 "$log_file" 2>/dev/null || true
      return 1
    fi
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

pid_alive() {
  local pid="$1"
  [[ -z "$pid" ]] || kill -0 "$pid" >/dev/null 2>&1
}

prepare_backend_privileges() {
  if [[ "$(id -u)" -eq 0 ]]; then
    BACKEND_PRIVILEGE_PREFIX=()
    return
  fi

  echo "Backend can quyen root de truy cap namespace Mininet."
  echo "Xac thuc sudo truoc khi khoi dong backend nen..."
  if ! sudo -v; then
    echo "FAIL Khong xac thuc duoc sudo; backend chua duoc khoi dong."
    return 1
  fi
  BACKEND_PRIVILEGE_PREFIX=(sudo -n -E)
}

wait_backend_health() {
  local pid="$1"
  local log_file="$2"
  local stable=0
  local health_file="$LOG_DIR/backend-health.json"
  for _ in {1..30}; do
    if ! pid_alive "$pid"; then
      echo "FAIL Backend process da dung truoc khi health san sang. Log cuoi:"
      tail -n 80 "$log_file" 2>/dev/null || true
      return 1
    fi
    if curl -fsS --max-time 3 http://127.0.0.1:8000/api/health > "$health_file" 2>/dev/null && \
       python3 - "$health_file" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
backend = payload.get("components", {}).get("backend", {})
raise SystemExit(0 if backend.get("status") == "online" else 1)
PY
    then
      stable=$((stable + 1))
      if [[ "$stable" -ge 2 ]]; then
        echo "OK   Backend /api/health on dinh; chi tiet component:"
        python3 - "$health_file" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
for name, item in payload.get("components", {}).items():
    print(f"  {name}: {item.get('status')} - {item.get('message_vi')}")
PY
        return 0
      fi
    else
      stable=0
    fi
    sleep 1
  done
  echo "FAIL Backend /api/health khong on dinh. Log cuoi:"
  tail -n 80 "$log_file" 2>/dev/null || true
  return 1
}

need_cmd python3
need_cmd node
need_cmd npm
need_cmd curl

NODE_MAJOR="$(node -p "Number(process.versions.node.split('.')[0])" 2>/dev/null || echo 0)"
if [[ "$NODE_MAJOR" -lt 18 ]]; then
  echo "Node.js hien tai qua cu: $(node -v 2>/dev/null || echo unknown)"
  echo "React/Vite can Node.js >= 18."
  echo
  echo "Cai Node.js 20 tren Ubuntu:"
  echo "  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -"
  echo "  sudo apt install -y nodejs"
  echo "  node -v"
  echo
  echo "Sau do cai lai frontend dependency:"
  echo "  cd $FRONTEND_DIR"
  echo "  rm -rf node_modules"
  echo "  npm install"
  exit 1
fi

if [[ -f "$PID_FILE" ]]; then
  ACTIVE_PID=0
  while IFS=: read -r _name pid; do
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" >/dev/null 2>&1; then
      ACTIVE_PID=1
      break
    fi
  done < "$PID_FILE"
  if [[ "$ACTIVE_PID" -eq 1 ]]; then
    echo "Da co demo process dang chay trong $PID_FILE"
    echo "Neu muon khoi dong lai, chay truoc:"
    echo "  ./scripts/stop_demo.sh"
    exit 1
  fi
  echo "Xoa PID file stale: $PID_FILE"
  rm -f "$PID_FILE"
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
  CONTROLLER_PID=""
else
  echo "Khoi dong OS-Ken Controller..."
  "$ROOT_DIR/sdn_mpls_demo/run_controller.sh" > "$LOG_DIR/controller.log" 2>&1 &
  CONTROLLER_PID=$!
  echo "controller:$CONTROLLER_PID" >> "$PID_FILE"
fi

if port_open 8000; then
  echo "Backend port 8000 da co san, khong khoi dong them backend."
  BACKEND_PID=""
else
  prepare_backend_privileges
  echo "Khoi dong FastAPI backend..."
  (
    cd "$BACKEND_DIR"
    "${BACKEND_PRIVILEGE_PREFIX[@]}" "$BACKEND_VENV/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
  ) > "$LOG_DIR/backend.log" 2>&1 &
  BACKEND_PID=$!
  echo "backend:$BACKEND_PID" >> "$PID_FILE"
fi

if port_open 5173; then
  echo "Frontend port 5173 da co san, khong khoi dong them frontend."
  FRONTEND_PID=""
else
  echo "Khoi dong React frontend..."
  (
    cd "$FRONTEND_DIR"
    npm run dev -- --host 0.0.0.0 --port 5173
  ) > "$LOG_DIR/frontend.log" 2>&1 &
  FRONTEND_PID=$!
  echo "frontend:$FRONTEND_PID" >> "$PID_FILE"
fi

wait_port "Controller" 6653 "$LOG_DIR/controller.log" "${CONTROLLER_PID:-}"
wait_port "Backend" 8000 "$LOG_DIR/backend.log" "${BACKEND_PID:-}"
wait_backend_health "${BACKEND_PID:-}" "$LOG_DIR/backend.log"
wait_port "Frontend" 5173 "$LOG_DIR/frontend.log" "${FRONTEND_PID:-}"
STARTUP_COMPLETE=1

VM_IPS="$(hostname -I 2>/dev/null | xargs || true)"

echo
echo "Da khoi dong dashboard."
echo "IT operator token:"
echo "  $CCH_DASHBOARD_OPERATOR_TOKEN"
echo "Nhap token nay vao o IT token tren dashboard de ping/iperf/block/link fail/policy toggle."
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
