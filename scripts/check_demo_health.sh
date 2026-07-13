#!/usr/bin/env bash
set -euo pipefail

check_port() {
  local name="$1"
  local port="$2"
  if timeout 2 bash -c "cat < /dev/null > /dev/tcp/127.0.0.1/$port" >/dev/null 2>&1; then
    echo "OK   $name port $port dang lang nghe"
  else
    echo "FAIL $name port $port chua san sang"
  fi
}

check_cmd() {
  local name="$1"
  local command="$2"
  if bash -lc "$command" >/dev/null 2>&1; then
    echo "OK   $name"
  else
    echo "FAIL $name"
  fi
}

check_port "Controller" 6653
check_port "Backend" 8000
check_port "Frontend" 5173
check_cmd "Open vSwitch" "command -v ovs-vsctl && ovs-vsctl show"
check_cmd "Mininet namespace" "pgrep -f 'mininet:'"

if command -v ovs-ofctl >/dev/null 2>&1 && ovs-vsctl br-exists core_hq >/dev/null 2>&1; then
  count="$(ovs-ofctl -O OpenFlow13 dump-flows core_hq 2>/dev/null | wc -l | tr -d ' ')"
  echo "OK   Flow count core_hq: $count"
else
  echo "FAIL Flow count: chua thay bridge core_hq"
fi

if command -v curl >/dev/null 2>&1; then
  curl -fsS http://127.0.0.1:8000/api/live/status >/dev/null && echo "OK   Backend API health" || echo "FAIL Backend API health"
else
  echo "SKIP Web/API check: chua co curl"
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
