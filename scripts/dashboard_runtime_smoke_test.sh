#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "FAIL Script runtime chi ho tro Linux/Ubuntu."
  exit 2
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "FAIL Can quyen root de doc namespace Mininet va OpenFlow flow."
  echo "Chay lai: sudo ./scripts/dashboard_runtime_smoke_test.sh"
  exit 2
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "FAIL Khong tim thay $PYTHON_BIN."
  exit 2
fi

exec "$PYTHON_BIN" "$ROOT_DIR/scripts/dashboard_runtime_smoke_test.py" "$@"
