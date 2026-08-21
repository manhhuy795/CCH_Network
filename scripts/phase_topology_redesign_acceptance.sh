#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[1/2] Static redesign validation"
"$PYTHON_BIN" "$ROOT_DIR/scripts/validate_redesigned_topology.py" || exit $?

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "[2/2] LIVE_RUNTIME_PENDING: Ubuntu/Mininet/OVS/OS-Ken required."
  exit 2
fi

echo "[2/2] Live redesign runtime validation"
"$PYTHON_BIN" "$ROOT_DIR/scripts/test_redesigned_topology_runtime.py"
"$PYTHON_BIN" "$ROOT_DIR/scripts/test_data_flows_runtime.py"
"$PYTHON_BIN" "$ROOT_DIR/scripts/test_ups_monitoring_runtime.py"
"$PYTHON_BIN" "$ROOT_DIR/scripts/test_mpls_failover_runtime.py"
"$PYTHON_BIN" "$ROOT_DIR/scripts/test_dhcp_runtime.py"
