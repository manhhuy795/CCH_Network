#!/usr/bin/env bash
set -euo pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONUTF8=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
RUNTIME_DIR="$SCRIPT_DIR/runtime"
CONTROLLER_LOG="$RUNTIME_DIR/controller.log"
LOCK_FILE="/tmp/cch-sdn-topology.lock"
CONTROLLER_PID=""
CONTROLLER_STARTED=0
MININET_ATTEMPTED=0

mkdir -p "$RUNTIME_DIR"
if [[ ! -w "$RUNTIME_DIR" ]]; then
  sudo chown -R "$(id -u):$(id -g)" "$RUNTIME_DIR" 2>/dev/null || true
fi
if [[ -f "$CONTROLLER_LOG" && ! -w "$CONTROLLER_LOG" ]]; then
  sudo rm -f "$CONTROLLER_LOG" 2>/dev/null || sudo chown "$(id -u):$(id -g)" "$CONTROLLER_LOG" 2>/dev/null || true
fi
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Loi: CCH topology dang chay o terminal khac."
  echo "Hay quay lai terminal Mininet hien tai hoac thoat phien cu truoc."
  exit 2
fi

controller_is_listening() {
  ss -H -ltn 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)6653$'
}

cleanup_v7_network() {
  local bridges=(
    access_floor1 access_floor2 core_hq access_branch dist_branch infra_access
    service_net ce_hq1 ce_hq2 ce_branch1 ce_branch2 l2vpn_primary l2vpn_backup
  )
  for bridge in "${bridges[@]}"; do
    sudo ovs-vsctl --if-exists del-br "$bridge" >/dev/null 2>&1 || true
    sudo ip link delete "$bridge" >/dev/null 2>&1 || true
  done
  sudo rm -f /var/run/netns/fw_hq /var/run/netns/fw_telesale >/dev/null 2>&1 || true
}

stop_auto_controller() {
  if [[ "$CONTROLLER_STARTED" -eq 1 && -n "$CONTROLLER_PID" ]]; then
    pkill -TERM -P "$CONTROLLER_PID" >/dev/null 2>&1 || true
    kill "$CONTROLLER_PID" >/dev/null 2>&1 || true
    wait "$CONTROLLER_PID" >/dev/null 2>&1 || true
  fi
}

cleanup_on_exit() {
  if [[ "$MININET_ATTEMPTED" -eq 1 ]]; then
    sudo mn -c >/dev/null 2>&1 || true
    cleanup_v7_network
  fi
  stop_auto_controller
}
trap cleanup_on_exit EXIT INT TERM

if pgrep -f "[t]opology_enterprise_v7.py" >/dev/null 2>&1; then
  echo "Loi: topology_enterprise_v7.py dang chay."
  exit 2
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Loi: chua co virtualenv OS-Ken tai $VENV_DIR"
  echo "Chay: ./sdn_mpls_demo/setup_ubuntu_24_04.sh"
  exit 1
fi
if ! command -v nft >/dev/null 2>&1; then
  echo "Loi: chua co nftables."
  exit 1
fi
if [[ ! -x "$VENV_DIR/bin/osken-manager" ]] || ! "$VENV_DIR/bin/python" -c "import os_ken.cmd.manager" >/dev/null 2>&1; then
  echo "Loi: OS-Ken runtime chua san sang trong $VENV_DIR"
  exit 1
fi

if controller_is_listening; then
  echo "Da co OpenFlow Controller tai 127.0.0.1:6653."
else
  echo "Khoi dong OS-Ken Controller..."
  : > "$CONTROLLER_LOG"
  nohup "$SCRIPT_DIR/run_controller.sh" >>"$CONTROLLER_LOG" 2>&1 &
  CONTROLLER_PID=$!
  CONTROLLER_STARTED=1
  for _ in $(seq 1 30); do
    controller_is_listening && break
    kill -0 "$CONTROLLER_PID" >/dev/null 2>&1 || break
    sleep 0.5
  done
  if ! controller_is_listening; then
    echo "Loi: OS-Ken khong mo duoc port 6653."
    tail -n 60 "$CONTROLLER_LOG" 2>/dev/null || true
    exit 1
  fi
fi

echo "Don Mininet/OVS cu..."
sudo mn -c >/dev/null 2>&1 || true
cleanup_v7_network

ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Khoi dong CCH Enterprise v7: 90 runtime users, VLAN 93 L2VPN Primary/Backup, IPsec L3 abstraction..."
MININET_ATTEMPTED=1
sudo env LANG="$LANG" LC_ALL="$LC_ALL" PYTHONUTF8="$PYTHONUTF8" PYTHONPATH="$ROOT_DIR" \
  python3 "$SCRIPT_DIR/topology_enterprise_v7.py"
