#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "PENDING Ubuntu runtime: script chi ho tro Linux/Ubuntu."
  exit 2
fi
if [[ "$(id -u)" -ne 0 ]]; then
  echo "FAIL Can quyen root de doc OVS, namespace va nftables."
  echo "Chay: sudo ./scripts/infrastructure_security_runtime_check.sh"
  exit 2
fi

exec "$PYTHON_BIN" "$ROOT_DIR/scripts/infrastructure_security_runtime_check.py" "$@"
