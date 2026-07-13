#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

cd "$BACKEND_DIR"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -r requirements.txt

HOST="${CCH_DASHBOARD_HOST:-0.0.0.0}"
PORT="${CCH_DASHBOARD_PORT:-8000}"
TOKEN="${CCH_DASHBOARD_TOKEN:-it-support-demo}"

echo "Khởi động dashboard backend tại http://$HOST:$PORT"
echo "Dashboard chỉ dành cho IT Support. Token lab hiện tại: $TOKEN"
echo "Nên chạy OS-Ken Controller và topology ở hai terminal khác trước."
exec sudo -E "$BACKEND_DIR/.venv/bin/python" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
