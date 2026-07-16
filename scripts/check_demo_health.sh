#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAILED=0

check_port() {
  local name="$1"
  local port="$2"
  if timeout 2 bash -c "cat < /dev/null > /dev/tcp/127.0.0.1/$port" >/dev/null 2>&1; then
    echo "OK   $name port $port dang lang nghe"
  else
    echo "FAIL $name port $port chua san sang"
    FAILED=1
  fi
}

check_cmd() {
  local name="$1"
  local command="$2"
  if bash -lc "$command" >/dev/null 2>&1; then
    echo "OK   $name"
  else
    echo "FAIL $name"
    FAILED=1
  fi
}

check_port "Controller" 6653
check_port "Backend" 8000
check_port "Frontend" 5173
check_cmd "Mininet topology process" "pgrep -f '[t]opology_hybrid_sdn.py'"

OVS_PREFIX=()
if [[ "$(id -u)" -ne 0 ]]; then
  if sudo -n true >/dev/null 2>&1; then
    OVS_PREFIX=(sudo -n)
  elif ovs-vsctl show >/dev/null 2>&1; then
    OVS_PREFIX=()
  else
    echo "Can quyen sudo de kiem tra Open vSwitch. Dang xac thuc sudo..."
    sudo -v
    OVS_PREFIX=(sudo)
  fi
fi

if command -v ovs-vsctl >/dev/null 2>&1 && "${OVS_PREFIX[@]}" ovs-vsctl show >/dev/null 2>&1; then
  echo "OK   Open vSwitch"
else
  echo "FAIL Open vSwitch khong san sang"
  FAILED=1
fi

if command -v ovs-ofctl >/dev/null 2>&1 && "${OVS_PREFIX[@]}" ovs-vsctl br-exists core_hq >/dev/null 2>&1; then
  count="$("${OVS_PREFIX[@]}" ovs-ofctl -O OpenFlow13 dump-flows core_hq 2>/dev/null | wc -l | tr -d ' ')"
  echo "OK   Flow count core_hq: $count"
else
  echo "FAIL Flow count: chua thay bridge core_hq"
  FAILED=1
fi

if command -v curl >/dev/null 2>&1; then
  HEALTH_FILE="$(mktemp)"
  trap 'rm -f "$HEALTH_FILE"' EXIT
  if curl -fsS --max-time 5 http://127.0.0.1:8000/api/health > "$HEALTH_FILE"; then
    python3 - "$HEALTH_FILE" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
for name, item in payload.get("components", {}).items():
    print(f"{item.get('status', 'unknown').upper():8} {name}: {item.get('message_vi', '')}")
PY
    if ! python3 - "$HEALTH_FILE" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
required = ("backend", "controller", "mininet_topology", "mininet_control_agent", "openvswitch")
components = payload.get("components", {})
raise SystemExit(0 if all(components.get(name, {}).get("status") == "online" for name in required) else 1)
PY
    then
      FAILED=1
    fi
  else
    echo "FAIL Backend API /api/health"
    FAILED=1
  fi
else
  echo "FAIL Web/API check: chua co curl"
  FAILED=1
fi

echo "WebSocket: kiem tra tren Dashboard bang nut Bat dau giam sat."
echo
echo "URL dung trong Ubuntu VM:"
echo "  Dashboard: http://127.0.0.1:5173"
echo "  Backend:   http://127.0.0.1:8000"
echo
echo "Neu FAIL, xem log:"
echo "  tail -n 80 logs/backend.log"
echo "  tail -n 80 logs/frontend.log"

exit "$FAILED"
