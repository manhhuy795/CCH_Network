#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/sdn_mpls_demo/.venv"

if [[ ! -f /etc/os-release ]]; then
  echo "Lỗi: không xác định được hệ điều hành."
  exit 1
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "24.04" ]]; then
  echo "Cảnh báo: script được kiểm thử cho Ubuntu 24.04 LTS; máy hiện tại là ${PRETTY_NAME:-không rõ}."
fi

echo "[1/4] Cài Mininet, Open vSwitch, Python 3.12 và công cụ đo kiểm"
sudo apt update
sudo apt install -y \
  git mininet openvswitch-switch iperf3 \
  python3 python3-venv python3-pip python3-dev \
  build-essential curl jq iproute2 procps

echo "[2/4] Bật Open vSwitch"
sudo systemctl enable --now openvswitch-switch

echo "[3/4] Tạo virtualenv riêng cho OS-Ken"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip wheel setuptools
"$VENV_DIR/bin/python" -m pip install --upgrade --force-reinstall \
  -r "$ROOT_DIR/sdn_mpls_demo/requirements.txt"

echo "[4/4] Kiểm tra công cụ"
python3 --version
mn --version
ovs-vsctl --version | head -n 1
iperf3 --version | head -n 1
"$VENV_DIR/bin/python" -c \
  "import os_ken, os_ken.cmd.manager; print('OS-Ken 3.1.1 + controller CLI: OK')"
test -x "$VENV_DIR/bin/osken-manager"

echo
echo "Cài đặt hoàn tất."
echo "Cách đơn giản nhất: sudo ./sdn_mpls_demo/run_topology.sh"
echo "Script topology sẽ tự khởi động OS-Ken nếu cổng 6653 chưa có controller."
