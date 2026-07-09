#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Lỗi: chưa có môi trường OS-Ken. Hãy chạy ./sdn_mpls_demo/setup_ubuntu_24_04.sh"
  exit 1
fi

mkdir -p "$SCRIPT_DIR/runtime"
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"

if ss -H -ltn 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)6653$'; then
  echo "Lỗi: cổng 6653 đang được một controller khác sử dụng."
  echo "Kiểm tra bằng: sudo ss -ltnp | grep :6653"
  exit 1
fi

echo "Khởi động OS-Ken Controller tại 127.0.0.1:6653"
echo "Nhấn Ctrl+C để dừng controller."

if [[ -x "$VENV_DIR/bin/osken-manager" ]]; then
  exec "$VENV_DIR/bin/osken-manager" \
    --ofp-listen-host 127.0.0.1 \
    --ofp-tcp-listen-port 6653 \
    "$SCRIPT_DIR/controller_policy.py"
fi

exec "$VENV_DIR/bin/python" -m os_ken.cmd.manager \
  --ofp-listen-host 127.0.0.1 \
  --ofp-tcp-listen-port 6653 \
  "$SCRIPT_DIR/controller_policy.py"
