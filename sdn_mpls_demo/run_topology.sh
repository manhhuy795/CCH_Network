#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
RUNTIME_DIR="$SCRIPT_DIR/runtime"
CONTROLLER_LOG="$RUNTIME_DIR/controller.log"
CONTROLLER_PID=""
CONTROLLER_STARTED=0

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

trap stop_auto_controller EXIT INT TERM

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

echo "Khởi động topology 100 user + 5 service..."
sudo python3 "$SCRIPT_DIR/topology_hybrid_sdn.py"
