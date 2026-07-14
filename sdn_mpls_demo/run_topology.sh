#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
RUNTIME_DIR="$SCRIPT_DIR/runtime"
CONTROLLER_LOG="$RUNTIME_DIR/controller.log"
CONTROLLER_PID=""
CONTROLLER_STARTED=0
MININET_ATTEMPTED=0
LOCK_FILE="/tmp/cch-sdn-topology.lock"

# Giá»¯ file descriptor 9 trong suá»‘t phiĂªn Mininet. Má»™t terminal thá»© hai sáº½
# dá»«ng ngay táº¡i Ä‘Ă¢y, trÆ°á»›c khi mn -c cĂ³ thá»ƒ phĂ¡ topology Ä‘ang hoáº¡t Ä‘á»™ng.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Lá»—i: topology CCH Ä‘ang cháº¡y á»Ÿ má»™t terminal khĂ¡c."
  echo "KhĂ´ng cháº¡y run_topology.sh láº§n thá»© hai."
  echo "Terminal má»›i nĂªn dĂ¹ng Ä‘á»ƒ cháº¡y dashboard:"
  echo "  ./dashboard/run_live_dashboard.sh"
  exit 2
fi

# Há»— trá»£ phĂ¡t hiá»‡n má»™t phiĂªn cÅ© Ä‘Æ°á»£c cháº¡y trÆ°á»›c khi project cĂ³ file lock.
if pgrep -f "[t]opology_hybrid_sdn.py" >/dev/null 2>&1; then
  echo "Lá»—i: Ä‘Ă£ tĂ¬m tháº¥y topology_hybrid_sdn.py Ä‘ang cháº¡y."
  echo "HĂ£y quay láº¡i terminal Mininet hiá»‡n táº¡i hoáº·c thoĂ¡t phiĂªn cÅ© trÆ°á»›c."
  exit 2
fi

controller_is_listening() {
  ss -H -ltn 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)6653$'
}

stop_auto_controller() {
  if [[ "$CONTROLLER_STARTED" -eq 1 && -n "$CONTROLLER_PID" ]]; then
    echo "Dá»«ng OS-Ken Controller do script tá»± khá»Ÿi Ä‘á»™ng..."
    pkill -TERM -P "$CONTROLLER_PID" >/dev/null 2>&1 || true
    kill "$CONTROLLER_PID" >/dev/null 2>&1 || true
    wait "$CONTROLLER_PID" >/dev/null 2>&1 || true
  fi
}

cleanup_stale_network() {
  local interfaces=(
    hqa-core core-hqa hqb-core core-hqb hqc-core core-hqc
    voice-core core-voice br-dist dist-access core-ce mpls-hq mpls-br
    dist-ce core-fw inet-hq dist-fw inet-br
    hqa-eth99 core-eth01 hqb-eth99 core-eth02 hqc-eth99 core-eth03
    hqi-eth99 core-eth07
    voice-eth99 core-eth04 br-eth99 dist-eth01 core-eth05
    hq_l3-eth0 hq_l3-eth1 hq_l3-eth2 ce_hq-eth0 ce_hq-eth1
    mpls-eth01 mpls-eth02 dist-eth02 branch_l3-eth0 branch_l3-eth1
    branch_l3-eth2 ce_branch-eth0 ce_branch-eth1 fw_hq-eth0 fw_hq-eth1
    fw_branch-eth0 fw_branch-eth1 inet-eth01 inet-eth02
  )
  local bridges=(
    access_hq_a access_hq_b access_hq_c access_hq_it voice_access core_hq
    access_branch dist_branch mpls_cloud internet
  )

  for interface in "${interfaces[@]}"; do
    sudo ovs-vsctl --if-exists del-port "$interface" >/dev/null 2>&1 || true
    sudo ip link delete "$interface" >/dev/null 2>&1 || true
  done
  for prefix in h20 h30 h40 h50 h60; do
    for index in $(seq -w 1 20); do
      interface="${prefix}-u${index}"
      sudo ovs-vsctl --if-exists del-port "$interface" >/dev/null 2>&1 || true
      sudo ip link delete "$interface" >/dev/null 2>&1 || true
    done
  done
  for index in $(seq -w 1 10); do
    interface="$(printf 'h70-u%02d' "$index")"
    sudo ovs-vsctl --if-exists del-port "$interface" >/dev/null 2>&1 || true
    sudo ip link delete "$interface" >/dev/null 2>&1 || true
  done
  sudo ip link delete voice-h90 >/dev/null 2>&1 || true
  sudo ip link delete voice-eth01 >/dev/null 2>&1 || true
  for bridge in "${bridges[@]}"; do
    sudo ovs-vsctl --if-exists del-br "$bridge" >/dev/null 2>&1 || true
  done
}

cleanup_on_exit() {
  if [[ "$MININET_ATTEMPTED" -eq 1 ]]; then
    sudo mn -c >/dev/null 2>&1 || true
    cleanup_stale_network
  fi
  stop_auto_controller
}

trap cleanup_on_exit EXIT INT TERM

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Lá»—i: chÆ°a cĂ³ virtualenv OS-Ken táº¡i $VENV_DIR"
  echo "HĂ£y cháº¡y: ./sdn_mpls_demo/setup_ubuntu_24_04.sh"
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/osken-manager" ]] || \
   ! "$VENV_DIR/bin/python" -c "import os_ken.cmd.manager" >/dev/null 2>&1; then
  echo "Lá»—i: virtualenv khĂ´ng cĂ³ OS-Ken Controller CLI tÆ°Æ¡ng thĂ­ch."
  echo "OS-Ken 4.x Ä‘Ă£ xĂ³a osken-manager; project sá»­ dá»¥ng OS-Ken 3.1.1."
  echo "HĂ£y cháº¡y láº¡i: ./sdn_mpls_demo/setup_ubuntu_24_04.sh"
  exit 1
fi

RUN_USER="${SUDO_USER:-$(id -un)}"
RUN_GROUP="$(id -gn "$RUN_USER")"

if [[ "$(id -u)" -eq 0 ]]; then
  install -d -o "$RUN_USER" -g "$RUN_GROUP" "$RUNTIME_DIR"
else
  mkdir -p "$RUNTIME_DIR"
fi

if controller_is_listening; then
  echo "ÄĂ£ tháº¥y OpenFlow Controller láº¯ng nghe táº¡i 127.0.0.1:6653."
else
  echo "ChÆ°a cĂ³ controller táº¡i cá»•ng 6653. Tá»± khá»Ÿi Ä‘á»™ng OS-Ken..."
  : > "$CONTROLLER_LOG"
  if [[ "$(id -u)" -eq 0 && -n "${SUDO_USER:-}" ]]; then
    chown "$RUN_USER:$RUN_GROUP" "$CONTROLLER_LOG"
    sudo -u "$RUN_USER" -H \
      nohup "$SCRIPT_DIR/run_controller.sh" \
      >>"$CONTROLLER_LOG" 2>&1 &
  else
    nohup "$SCRIPT_DIR/run_controller.sh" \
      >>"$CONTROLLER_LOG" 2>&1 &
  fi
  CONTROLLER_PID=$!
  CONTROLLER_STARTED=1

  for _ in $(seq 1 30); do
    if controller_is_listening; then
      break
    fi
    if ! kill -0 "$CONTROLLER_PID" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done

  if ! controller_is_listening; then
    echo
    echo "Lá»—i: OS-Ken khĂ´ng má»Ÿ Ä‘Æ°á»£c cá»•ng 6653."
    echo "Log controller: $CONTROLLER_LOG"
    echo "---------------- 40 dĂ²ng log cuá»‘i ----------------"
    tail -n 40 "$CONTROLLER_LOG" 2>/dev/null || true
    echo "---------------------------------------------------"
    exit 1
  fi
  echo "OS-Ken Ä‘Ă£ sáºµn sĂ ng táº¡i 127.0.0.1:6653."
fi

echo "Dá»n tráº¡ng thĂ¡i Mininet cÅ©..."
sudo mn -c >/dev/null 2>&1 || true
cleanup_stale_network

echo "Khá»Ÿi Ä‘á»™ng topology 110 user + 5 service..."
MININET_ATTEMPTED=1
sudo python3 "$SCRIPT_DIR/topology_hybrid_sdn.py"
