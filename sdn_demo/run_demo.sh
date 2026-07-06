#!/usr/bin/env bash
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${DEMO_DIR}/.." && pwd)"
CONTROLLER_LOG="${DEMO_DIR}/controller.log"

cd "${REPO_ROOT}"

if command -v osken-manager >/dev/null 2>&1; then
  MANAGER="osken-manager"
elif command -v ryu-manager >/dev/null 2>&1; then
  MANAGER="ryu-manager"
else
  echo "Could not find osken-manager or ryu-manager. Install OS-Ken/Ryu first."
  exit 1
fi

cleanup() {
  if [[ -n "${CTRL_PID:-}" ]]; then
    kill "${CTRL_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "[1/4] Cleaning old Mininet state"
sudo mn -c >/dev/null 2>&1 || true

echo "[2/4] Starting SDN controller with ${MANAGER} on 127.0.0.1:6653"
"${MANAGER}" sdn_demo/controller_callcenter_policy.py --ofp-tcp-listen-port 6653 >"${CONTROLLER_LOG}" 2>&1 &
CTRL_PID=$!
sleep 3

echo "[3/4] Starting Mininet topology"
echo "Controller log: ${CONTROLLER_LOG}"
echo "Inside Mininet, copy/paste commands from: sdn_demo/test_commands.txt"
echo
sudo python3 sdn_demo/topology_callcenter.py

echo "[4/4] Cleaning Mininet state"
sudo mn -c >/dev/null 2>&1 || true
