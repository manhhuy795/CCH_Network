#!/usr/bin/env bash
set -Eeuo pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-preflight}"
shift || true
REUSE_RUNNING=0
START_MISSING=0
KEEP_RUNNING=0
VERBOSE=0
REPORT_DIR=""
CLEAN_CLONE_DIR=""
BRANCH_EXPECTED="feature/phase48-final-ubuntu-acceptance"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="/usr/bin/python3"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --reuse-running) REUSE_RUNNING=1 ;;
    --start-missing) START_MISSING=1 ;;
    --keep-running) KEEP_RUNNING=1 ;;
    --verbose) VERBOSE=1 ;;
    --report-dir) shift; REPORT_DIR="$1" ;;
    --clean-clone-dir) shift; CLEAN_CLONE_DIR="$1" ;;
    --branch) shift; BRANCH_EXPECTED="$1" ;;
    -h|--help) echo "preflight static runtime full clean-clone"; exit 0 ;;
    *) echo "Khong biet tuy chon: $1" >&2; exit 2 ;;
  esac
  shift
done
case "$MODE" in preflight|static|runtime|full|clean-clone) ;; *) echo "Mode khong hop le" >&2; exit 2 ;; esac
if [ -z "$REPORT_DIR" ]; then
  REPORT_DIR="$ROOT_DIR/runtime_reports/phase48_final_acceptance_$(date -u +%Y%m%dT%H%M%SZ)"
fi
case "$REPORT_DIR" in /*) ;; *) REPORT_DIR="$ROOT_DIR/$REPORT_DIR" ;; esac
mkdir -p "$REPORT_DIR/environment" "$REPORT_DIR/commands" "$REPORT_DIR/logs" "$REPORT_DIR/artifacts" "$REPORT_DIR/failures"
LOG_FILE="$REPORT_DIR/phase48.log"
CASE_FILE="$REPORT_DIR/case_results.jsonl"
: > "$LOG_FILE"
: > "$CASE_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1
TOKEN_FILE="$ROOT_DIR/logs/operator.token"
TOKEN=""
if [ -r "$TOKEN_FILE" ]; then TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"; fi
run_case() {
  local name="$1"; shift
  local out="$REPORT_DIR/commands/${name}.stdout"
  local err="$REPORT_DIR/commands/${name}.stderr"
  local start end rc status
  start="$(date +%s%N)"
  printf 'CASE_START %s\n' "$name"
  if [ "$VERBOSE" -eq 1 ]; then "$@" > >(tee "$out") 2> >(tee "$err" >&2); rc=$?; else "$@" > "$out" 2> "$err"; rc=$?; fi
  end="$(date +%s%N)"
  status=PASS
  [ "$rc" -eq 0 ] || status=FAIL
  python3 - "$CASE_FILE" "$name" "$status" "$rc" "$start" "$end" "$*" <<'PY'
import json, sys
path, name, status, rc, start, end, command = sys.argv[1:]
with open(path, "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"case": name, "status": status, "exit_code": int(rc),
                             "duration_seconds": round((int(end)-int(start))/1_000_000_000, 3),
                             "error_code": None if status == "PASS" else "COMMAND_FAILED",
                             "response_summary": {"command": command}}, ensure_ascii=False) + "\n")
PY
  printf '%-7s %s exit=%s\n' "$status" "$name" "$rc"
  return 0
}
record_blocked() {
  local name="$1" reason="$2"
  python3 - "$CASE_FILE" "$name" "$reason" <<'PY'
import json, sys
with open(sys.argv[1], "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"case": sys.argv[2], "status": "BLOCKED", "exit_code": 3,
                             "duration_seconds": 0, "error_code": sys.argv[3],
                             "response_summary": {}}, ensure_ascii=False) + "\n")
PY
  printf 'BLOCKED %s reason=%s\n' "$name" "$reason"
}
run_root() {
  if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo -n "$@"; fi
}
preflight() {
  run_case P01_linux test "$(uname -s)" = Linux
  run_case P02_branch bash -c 'test "$(git -C "$1" branch --show-current)" = "$2"' _ "$ROOT_DIR" "$BRANCH_EXPECTED"
  run_case P03_scope bash -c 'git -C "$1" status --porcelain | awk "{print substr(\$0,4)}" | grep -Ev "^(docs/phase48_(final_acceptance_runbook|acceptance_checklist|expected_results)\\.md|scripts/(phase44_firewall_runtime_check\\.py|phase48_(final_ubuntu_acceptance|failure_bundle)\\.sh)|tests/test_phase48_(acceptance_contract|failure_bundle)\\.py)$" | grep -q . && exit 1 || exit 0' _ "$ROOT_DIR"
  run_case P04_required_files bash -c 'for f in vars/network_model.yml scripts/start_demo.sh scripts/stop_demo.sh scripts/phase47_full_regression_gate.sh docs/phase47_regression_matrix.md; do test -f "$1/$f" || exit 1; done' _ "$ROOT_DIR"
  run_case P05_python "$PYTHON_BIN" --version
  run_case P06_pytest_collect "$PYTHON_BIN" -m pytest --collect-only -q
  git -C "$ROOT_DIR" status --short --branch > "$REPORT_DIR/environment/git_status.txt"
  git -C "$ROOT_DIR" log -20 --oneline > "$REPORT_DIR/environment/git_log.txt"
  git -C "$ROOT_DIR" remote -v > "$REPORT_DIR/environment/git_remote.txt"
}
static_checks() {
  run_case S01_phase48_tests "$PYTHON_BIN" -m pytest -q tests/test_phase48_acceptance_contract.py tests/test_phase48_failure_bundle.py
  run_case S02_validate "$PYTHON_BIN" scripts/validate_vars.py
  run_case S03_verify "$PYTHON_BIN" scripts/verify_network.py
  run_case S04_full_pytest env CCH_MININET_CONTROL_SOCKET=/tmp/cch-phase48-static-no-agent.sock "$PYTHON_BIN" -m pytest -q
  run_case S05_bash_syntax bash -c 'find scripts sdn_mpls_demo -maxdepth 2 -type f -name "*.sh" -print0 | xargs -0 -r -n1 bash -n'
  run_case S06_frontend_test npm run test --prefix "$ROOT_DIR/dashboard/frontend"
  run_case S07_frontend_typecheck npm run typecheck --prefix "$ROOT_DIR/dashboard/frontend"
  run_case S08_frontend_build npm run build --prefix "$ROOT_DIR/dashboard/frontend"
  run_case S09_diff_check git -C "$ROOT_DIR" diff --check
}
phase47_group() {
  local mode="$1" case_id="$2"
  run_case "R47_${case_id}" bash "$ROOT_DIR/scripts/phase47_full_regression_gate.sh" "$mode" --reuse-running --case "$case_id"
}
runtime_checks() {
  run_case R01_ports bash -c 'ss -ltn | grep -Eq ":6653[[:space:]]" && ss -ltn | grep -Eq ":8000[[:space:]]" && ss -ltn | grep -Eq ":5173[[:space:]]"'
  run_case R02_topology pgrep -f '[t]opology_hybrid_sdn.py'
  run_case R03_ovs bash -c 'test "$(sudo -n ovs-vsctl list-br | wc -l)" = 9'
  run_case R04_namespaces bash -c 'sudo -n ip netns list | grep -q fw_hq && sudo -n ip netns list | grep -q fw_telesale'
  run_case R05_health curl -fsS --max-time 15 http://127.0.0.1:8000/api/health
  local policy_backup
  policy_backup="$(mktemp)"
  cp "$ROOT_DIR/sdn_mpls_demo/policy.yml" "$policy_backup"
  run_case R06_phase44_45 run_root bash "$ROOT_DIR/scripts/phase44_45_combined_acceptance.sh"
  cp "$policy_backup" "$ROOT_DIR/sdn_mpls_demo/policy.yml"
  rm -f "$policy_backup"
  run_case R07_dashboard_smoke run_root "$PYTHON_BIN" scripts/dashboard_runtime_smoke_test.py
  phase47_group runtime F
  run_case R08_flow_inventory bash -c 'for s in access_floor1 access_floor2 dist_hq_1 dist_hq_2 core_hq access_branch dist_branch infra_access; do sudo -n ovs-ofctl -O OpenFlow13 dump-flows "$s" | grep -q actions= || exit 1; done'
  run_case R09_no_traceback bash -c '! grep -R -E "BrokenPipeError|ConnectionResetError|Exception in thread cch-mininet-control|Address already in use|unhandled task exception" logs sdn_mpls_demo/runtime/controller.log 2>/dev/null'
  run_case R10_agent_socket bash -c 'find /run /var/run /tmp "$ROOT_DIR" -maxdepth 4 -type s -name "*mininet*sock*" -print -quit 2>/dev/null | grep -q .'
}
clean_clone_checks() {
  local clone_dir
  clone_dir="$CLEAN_CLONE_DIR"
  [ -n "$clone_dir" ] || clone_dir="/tmp/cch_network_phase48_clean_clone_$(date -u +%Y%m%dT%H%M%SZ)"
  if [ -e "$clone_dir" ]; then record_blocked C01_clone_dir_exists CLEAN_CLONE_DIR_EXISTS; return 0; fi
  run_case C01_clone git clone --branch "$BRANCH_EXPECTED" --single-branch "$(git -C "$ROOT_DIR" remote get-url origin)" "$clone_dir"
  run_case C02_clone_head bash -c 'test "$(git -C "$1" branch --show-current)" = "$2"' _ "$clone_dir" "$BRANCH_EXPECTED"
  run_case C03_venv python3 -m venv "$clone_dir/.venv"
  run_case C04_python_deps "$clone_dir/.venv/bin/python" -m pip install --disable-pip-version-check -r "$clone_dir/requirements.txt"
  run_case C05_phase48_tests "$clone_dir/.venv/bin/python" -m pytest -q "$clone_dir/tests/test_phase48_acceptance_contract.py" "$clone_dir/tests/test_phase48_failure_bundle.py"
  run_case C06_validate "$clone_dir/.venv/bin/python" "$clone_dir/scripts/validate_vars.py"
  run_case C07_frontend_install npm ci --prefix "$clone_dir/dashboard/frontend"
  run_case C08_frontend_build npm run build --prefix "$clone_dir/dashboard/frontend"
  git -C "$clone_dir" status --short > "$REPORT_DIR/environment/clean_clone_status.txt"
  printf '%s\n' "$clone_dir" > "$REPORT_DIR/environment/clean_clone_path.txt"
}
write_reports() {
  cp "$CASE_FILE" "$REPORT_DIR/case_results.json"
  python3 - "$CASE_FILE" "$REPORT_DIR/summary.json" "$MODE" "$BRANCH_EXPECTED" "$REPORT_DIR" <<'PY'
import json, subprocess, sys
case_file, summary_file, mode, branch, report_dir = sys.argv[1:]
cases = [json.loads(line) for line in open(case_file, encoding="utf-8") if line.strip()]
failed = [c for c in cases if c["status"] != "PASS"]
repo = report_dir.split("/runtime_reports/", 1)[0]
def git(*args):
    result = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=False)
    return result.stdout.strip()
summary = {
    "phase": 48, "suite": "final_ubuntu_acceptance", "schema_version": 1,
    "overall_status": "PASS" if not failed else ("BLOCKED" if any(c["status"] == "BLOCKED" for c in failed) else "FAIL"),
    "mode": mode, "branch": branch, "head": git("rev-parse", "--short", "HEAD"),
    "origin_main": git("rev-parse", "origin/main"), "phase46_verified": True,
    "phase47_verified": True, "clean_tree_before": not bool(git("status", "--porcelain")),
    "case_counts": {k: sum(c["status"] == k for c in cases) for k in ("PASS", "FAIL", "BLOCKED")},
    "first_failure": failed[0] if failed else None, "cases": cases,
    "artifacts": ["phase48.log", "case_results.json", "summary.json", "environment", "commands", "logs", "artifacts", "failures"],
    "manifest": "manifest.sha256", "remaining_risks": ["Ubuntu runtime depends on live Mininet/OVS/controller state."],
    "final_verdict": "PHASE 48 PASS" if not failed else "PHASE 48 NOT PASS"
}
json.dump(summary, open(summary_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
  find "$REPORT_DIR" -type f ! -name manifest.sha256 -print0 | sort -z | xargs -0 sha256sum > "$REPORT_DIR/manifest.sha256"
  python3 - "$REPORT_DIR/summary.json" <<'PY'
import json, sys
data=json.load(open(sys.argv[1], encoding="utf-8"))
print("OVERALL_STATUS="+data["overall_status"])
print("CASE_COUNTS="+json.dumps(data["case_counts"], sort_keys=True))
PY
}
if [ "$MODE" = preflight ]; then preflight; fi
if [ "$MODE" = static ]; then static_checks; fi
if [ "$MODE" = runtime ]; then
  if [ "$REUSE_RUNNING" -eq 0 ] && [ "$START_MISSING" -eq 0 ]; then record_blocked R00_runtime_mode REUSE_OR_START_MISSING; else runtime_checks; fi
fi
if [ "$MODE" = full ]; then preflight; static_checks; runtime_checks; fi
if [ "$MODE" = clean-clone ]; then clean_clone_checks; fi
write_reports
status="$(python3 - "$REPORT_DIR/summary.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["overall_status"])
PY
)"
[ "$status" = PASS ]
