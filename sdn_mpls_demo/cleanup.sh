#!/usr/bin/env bash
set -euo pipefail

echo "Dọn Mininet và bridge/interface còn sót..."
sudo mn -c
sudo rm -f /var/run/netns/fw_hq /var/run/netns/fw_telesale
echo "Đã cleanup. Controller chạy ở terminal riêng có thể dừng bằng Ctrl+C."
