#!/usr/bin/env bash
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${DEMO_DIR}/.." && pwd)"
CONTROLLER_LOG="${DEMO_DIR}/controller.log"
TOPOLOGY_PYTHON="${TOPOLOGY_PYTHON:-python3}"

cd "${REPO_ROOT}"

if command -v osken-manager >/dev/null 2>&1; then
  MANAGER_CMD=(osken-manager)
elif command -v ryu-manager >/dev/null 2>&1; then
  MANAGER_CMD=(ryu-manager)
elif python -c "import os_ken" >/dev/null 2>&1; then
  MANAGER_CMD=(python -m os_ken.cmd.manager)
elif python -c "import ryu" >/dev/null 2>&1; then
  MANAGER_CMD=(python -m ryu.cmd.manager)
else
  echo "Could not find OS-Ken or Ryu. Run: ./sdn_demo/setup_ubuntu_vm_vi.sh"
  exit 1
fi

cleanup() {
  if [[ -n "${CTRL_PID:-}" ]]; then
    kill "${CTRL_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

wait_for_controller() {
  local retries=10
  local delay=1

  for _ in $(seq 1 "${retries}"); do
    if ! kill -0 "${CTRL_PID}" >/dev/null 2>&1; then
      echo "SDN controller da dung/crash. Xem log:"
      echo "  cat ${CONTROLLER_LOG}"
      echo
      tail -n 80 "${CONTROLLER_LOG}" || true
      exit 1
    fi

    if command -v ss >/dev/null 2>&1; then
      if ss -ltn | grep -q ':6653 '; then
        return
      fi
    elif command -v netstat >/dev/null 2>&1; then
      if netstat -ltn | grep -q ':6653 '; then
        return
      fi
    else
      sleep "${delay}"
      return
    fi

    sleep "${delay}"
  done

  echo "Khong thay controller listen tren 127.0.0.1:6653 sau ${retries} giay."
  echo "Xem log:"
  echo "  cat ${CONTROLLER_LOG}"
  echo
  tail -n 80 "${CONTROLLER_LOG}" || true
  exit 1
}

echo "[1/4] Cleaning old Mininet state"
sudo mn -c >/dev/null 2>&1 || true

echo "[2/4] Starting SDN controller with ${MANAGER_CMD[*]} on 127.0.0.1:6653"
"${MANAGER_CMD[@]}" sdn_demo/controller_callcenter_policy.py --ofp-tcp-listen-port 6653 >"${CONTROLLER_LOG}" 2>&1 &
CTRL_PID=$!
wait_for_controller

echo "[3/4] Starting Mininet topology"
echo "Controller log: ${CONTROLLER_LOG}"
echo "Inside Mininet, copy/paste commands from: sdn_demo/test_commands.txt"
echo
sudo "${TOPOLOGY_PYTHON}" sdn_demo/topology_callcenter.py

echo "[4/4] Cleaning Mininet state"
sudo mn -c >/dev/null 2>&1 || true
