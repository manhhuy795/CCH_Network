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

# Giữ file descriptor 9 trong suốt phiên Mininet. Một terminal thứ hai sẽ
# dừng ngay tại đây, trước khi mn -c có thể phá topology đang hoạt động.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Lỗi: topology CCH đang chạy ở một terminal khác."
  echo "Không chạy run_topology.sh lần thứ hai."
  echo "Terminal mới nên dùng để chạy dashboard:"
  echo "  ./dashboard/run_live_dashboard.sh"
  exit 2
fi

# Hỗ trợ phát hiện một phiên cũ được chạy trước khi project có file lock.
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
    hqa-core core-hqa hqb-core core-hqb hqc-core core-hqc
    voice-core core-voice br-dist dist-access core-ce mpls-hq mpls-br
    dist-ce core-fw inet-hq dist-fw inet-br
    hqa-eth99 core-eth01 hqb-eth99 core-eth02 hqc-eth99 core-eth03
    hqi-eth99 core-eth07
    voice-eth99 core-eth04 br-eth99 dist-eth01 core-eth05
    mpls-eth01 mpls-eth02 dist-eth02 core-eth06 inet-eth01
    dist-eth03 inet-eth02
  )
  local bridges=(
    access_hq_a access_hq_b access_hq_c access_hq_it voice_mgmt core_hq
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
  echo "Lỗi: chưa có virtualenv OS-Ken tại $VENV_DIR"
  echo "Hãy chạy: ./sdn_mpls_demo/setup_ubuntu_24_04.sh"
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
  echo "Đã thấy OpenFlow Controller lắng nghe tại 127.0.0.1:6653."
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
MININET_ATTEMPTED=1
sudo python3 "$SCRIPT_DIR/topology_hybrid_sdn.py"
