#!/usr/bin/env bash
set -euo pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONUTF8=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
RUNTIME_DIR="$SCRIPT_DIR/runtime"
CONTROLLER_LOG="$RUNTIME_DIR/controller.log"
RESOURCE_BASELINE="$RUNTIME_DIR/phase42_resource_baseline.log"
CONTROLLER_PID=""
CONTROLLER_STARTED=0
MININET_ATTEMPTED=0
LOCK_FILE="/tmp/cch-sdn-topology.lock"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Lỗi : CCH đang chạy ở terminal khác."
  echo "Hãy quay lại terminal Mininet hiện tại hoặc thoát phiên cũ trước."
  echo "Terminal mới nên dùng để chạy dashboard:"
  echo "  ./dashboard/run_live_dashboard.sh"
  exit 2
fi

if pgrep -f "[t]opology_hybrid_sdn.py" >/dev/null 2>&1; then
  echo "Lỗi: đã tìm thấy topology_hybrid_sdn.py đang chạy."
  echo "Hãy quay lại terminal Mininet hiện tại hoặc thoát phiên cũ trước."
  exit 2
fi

controller_is_listening() {
  ss -H -ltn 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)6653$'
}

stop_auto_controller() {
  if [[ "$CONTROLLER_STARTED" -eq 1 && -n "$CONTROLLER_PID" ]]; then
    echo "Dừng OS-Ken Controller do script tự khởi động..."
    pkill -TERM -P "$CONTROLLER_PID" >/dev/null 2>&1 || true
    kill "$CONTROLLER_PID" >/dev/null 2>&1 || true
    wait "$CONTROLLER_PID" >/dev/null 2>&1 || true
  fi
}

cleanup_stale_network() {
  local interfaces=(
    hqa-eth99 core-eth01 hqb-eth99 core-eth02 hqc-eth99 core-eth03
    hqi-eth99 core-eth07 voice-eth99 core-eth04 bo-eth99 core-eth06
    tel-eth99 tdist-eth01 core-eth05
    hq_l3-eth0 hq_l3-eth1 hq_l3-eth2 ce_hq-eth0 ce_hq-eth1
    mpls-eth0 mpls-eth1 tdist-eth02 tele_l3-eth0 tele_l3-eth1
    tele_l3-eth2 ce_tel-eth0 ce_tel-eth1 fw_hq-eth0 fw_hq-eth1
    fw_tel-eth0 fw_tel-eth1 inet-eth0 inet-eth1 inet-eth2 svc-zone
    svc-zalo svc-call svc-social svc-inet
  )
  local bridges=(
    access_hq_a access_hq_b access_hq_c access_hq_it voice_access core_hq
    access_telesale dist_telesale access_bo service_net
  )
  # Migration-only cleanup for bridges created by pre-Phase-42 runtimes.
  local legacy_bridges=(
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
    interface="h70-u${index}"
    sudo ovs-vsctl --if-exists del-port "$interface" >/dev/null 2>&1 || true
    sudo ip link delete "$interface" >/dev/null 2>&1 || true
  done
  sudo ip link delete voice-h90 >/dev/null 2>&1 || true
  sudo ip link delete voice-eth01 >/dev/null 2>&1 || true
  for bridge in "${bridges[@]}"; do
    sudo ovs-vsctl --if-exists del-br "$bridge" >/dev/null 2>&1 || true
    sudo ip link delete "$bridge" >/dev/null 2>&1 || true
  done
  for bridge in "${legacy_bridges[@]}"; do
    sudo ovs-vsctl --if-exists del-br "$bridge" >/dev/null 2>&1 || true
  done
}

cleanup_on_exit() {
  sudo rm -f /var/run/netns/fw_hq /var/run/netns/fw_telesale >/dev/null 2>&1 || true
  if [[ "$MININET_ATTEMPTED" -eq 1 ]]; then
    sudo mn -c >/dev/null 2>&1 || true
    cleanup_stale_network
  fi
  stop_auto_controller
}

trap cleanup_on_exit EXIT INT TERM

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Lỗi: chưa có virtualenv OS-Ken tại $VENV_DIR"
  echo "Hãy chạy: ./sdn_mpls_demo/setup_ubuntu_24_04.sh"
  exit 1
fi

if ! command -v nft >/dev/null 2>&1; then
  echo "Lỗi: chưa có nftables. Hãy chạy lại ./sdn_mpls_demo/setup_ubuntu_24_04.sh"
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/osken-manager" ]] || \
   ! "$VENV_DIR/bin/python" -c "import os_ken.cmd.manager" >/dev/null 2>&1; then
  echo "Lỗi: virtualenv không có OS-Ken Controller CLI tương thích."
  echo "OS-Ken 4.x đã xóa osken-manager; project sử dụng OS-Ken 3.1.1."
  echo "Hãy chạy lại: ./sdn_mpls_demo/setup_ubuntu_24_04.sh"
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
  echo "Đã thấy OpenFlow Controller đang lắng nghe tại 127.0.0.1:6653."
else
  echo "Chưa có controller tại cổng 6653. Tự khởi động OS-Ken..."
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
    echo "Lỗi: OS-Ken không mở được cổng 6653."
    echo "Log controller: $CONTROLLER_LOG"
    echo "---------------- 40 dòng log cuối ----------------"
    tail -n 40 "$CONTROLLER_LOG" 2>/dev/null || true
    echo "---------------------------------------------------"
    exit 1
  fi
  echo "OS-Ken đã sẵn sàng tại 127.0.0.1:6653."
fi

echo "Dọn trạng thái Mininet cũ..."
sudo mn -c >/dev/null 2>&1 || true
cleanup_stale_network

echo "Khởi động topology 110 user + 5 service..."
{
  echo "PHASE 42 RESOURCE BASELINE"
  date --iso-8601=seconds
  echo "--- free -m ---"
  free -m
  echo "EXIT_CODE=$?"
  echo "--- swapon --show ---"
  swapon --show
  echo "EXIT_CODE=$?"
  echo "--- ps top RSS ---"
  ps -eo pid,ppid,%cpu,%mem,rss,cmd --sort=-rss | sed -n '1,30p'
  echo "--- ps top CPU ---"
  ps -eo pid,ppid,%cpu,%mem,rss,cmd --sort=-%cpu | sed -n '1,30p'
} | tee "$RESOURCE_BASELINE"
MININET_ATTEMPTED=1
sudo env LANG="$LANG" LC_ALL="$LC_ALL" PYTHONUTF8="$PYTHONUTF8" \
  python3 "$SCRIPT_DIR/topology_hybrid_sdn.py"
