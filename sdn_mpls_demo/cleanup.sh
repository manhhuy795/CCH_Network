#!/usr/bin/env bash
set -euo pipefail

echo "Dọn Mininet và bridge/interface còn sót..."
sudo mn -c
echo "Đã cleanup. Controller chạy ở terminal riêng có thể dừng bằng Ctrl+C."
