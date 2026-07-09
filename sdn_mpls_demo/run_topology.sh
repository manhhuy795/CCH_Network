#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! pgrep -f "os_ken.cmd.manager|osken-manager.*controller_policy.py" >/dev/null; then
  echo "Lỗi: chưa thấy OS-Ken Controller. Hãy chạy run_controller.sh ở terminal khác."
  exit 1
fi

echo "Dọn trạng thái Mininet cũ..."
sudo mn -c >/dev/null 2>&1 || true

echo "Khởi động topology 100 user + 5 service..."
exec sudo python3 "$SCRIPT_DIR/topology_hybrid_sdn.py"
