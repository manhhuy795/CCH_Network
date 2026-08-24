#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${1:-full}"
shift || true
PYTHON_BIN="${CCH_TEST_PYTHON:-$ROOT_DIR/.venv/bin/python}"
[[ -x "$PYTHON_BIN" ]] || PYTHON_BIN="$(command -v python3)"

# Kept for CLI compatibility with the old gate. v7 does not silently start or
# mutate runtime processes; start the demo explicitly before runtime checks.
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --reuse-running|--verbose) ;;
    --start-missing)
      echo "BLOCKED: v7 gate does not auto-start runtime; run sdn_mpls_demo/run_topology.sh and scripts/start_demo.sh first." >&2
      exit 3
      ;;
    --report-dir|--case) shift ;;
    -h|--help)
      echo "Usage: $0 {preflight|source|static|frontend|automation|runtime|full}"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

case "$MODE" in
  preflight|source|static|frontend|automation|runtime|full) ;;
  *) echo "Unknown mode: $MODE" >&2; exit 2 ;;
esac

run() {
  echo "+ $*"
  "$@"
}

static_checks() {
  run "$PYTHON_BIN" scripts/validate_vars.py
  run "$PYTHON_BIN" scripts/validate_redesigned_topology.py
  run "$PYTHON_BIN" -c 'from scripts.phase46_automation_docs_gate import ROOT_DIR, docs_reference_errors; errors=docs_reference_errors(ROOT_DIR); print("\n".join(errors)); raise SystemExit(bool(errors))'
  run "$PYTHON_BIN" -c 'from scripts.phase46_automation_docs_gate import ROOT_DIR, secret_scan; errors=secret_scan(ROOT_DIR); print("\n".join(errors)); raise SystemExit(bool(errors))'

  local tmp_dir
  tmp_dir="$(mktemp -d)"
  run "$PYTHON_BIN" scripts/generate_configs.py --output-dir "$tmp_dir"
  run "$PYTHON_BIN" scripts/verify_network.py --config-dir "$tmp_dir"
  rm -rf "$tmp_dir"

  run "$PYTHON_BIN" -m pytest -q
  run git diff --check
  if git ls-files | grep -Eq '(^|/)(runtime_reports|logs|\.venv|node_modules)/|\.pid$|\.sock$|operator\.token$|\.pem$|\.key$'; then
    echo "FAIL: runtime artifact or secret-like file is tracked by git." >&2
    exit 1
  fi
}

frontend_checks() {
  run npm run test --prefix dashboard/frontend
  run npm run typecheck --prefix dashboard/frontend
  run npm run build --prefix dashboard/frontend
}

runtime_checks() {
  command -v mn >/dev/null || { echo "BLOCKED: Mininet is not installed." >&2; exit 3; }
  command -v ovs-vsctl >/dev/null || { echo "BLOCKED: Open vSwitch is not installed." >&2; exit 3; }
  pgrep -f '[t]opology_enterprise_v7.py' >/dev/null || {
    echo "BLOCKED: enterprise v7 topology is not running." >&2
    exit 3
  }

  local expected actual
  expected="access_branch access_floor1 access_floor2 core_hq dist_branch infra_access"
  actual="$(sudo -n ovs-vsctl list-br | sort | xargs)"
  [[ "$actual" == "$expected" ]] || {
    echo "FAIL: expected six v7 OVS bridges: $expected" >&2
    echo "FAIL: actual bridges: $actual" >&2
    exit 1
  }

  run "$PYTHON_BIN" scripts/mininet_dashboard_preflight.py
  run curl -fsS http://127.0.0.1:8000/api/health
}

case "$MODE" in
  preflight)
    run "$PYTHON_BIN" scripts/validate_vars.py
    run "$PYTHON_BIN" scripts/validate_redesigned_topology.py
    ;;
  source|static|automation) static_checks ;;
  frontend) frontend_checks ;;
  runtime) runtime_checks ;;
  full)
    static_checks
    frontend_checks
    runtime_checks
    ;;
esac

echo "PASS: enterprise v7 $MODE gate"
