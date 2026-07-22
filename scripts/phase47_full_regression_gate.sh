#!/usr/bin/env bash
set -o pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODE="$1"
shift
REUSE_RUNNING=0
START_MISSING=0
VERBOSE=0
REPORT_DIR=""
CASE_FILTER=""
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="$(command -v python3)"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --reuse-running) REUSE_RUNNING=1 ;;
    --start-missing) START_MISSING=1 ;;
    --verbose) VERBOSE=1 ;;
    --report-dir) shift; REPORT_DIR="$1" ;;
    --case) shift; CASE_FILTER="$1" ;;
    -h|--help) echo "preflight source static frontend automation runtime full"; exit 0 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
case "$MODE" in preflight|source|static|frontend|automation|runtime|full) ;; *) exit 2 ;; esac
[ -n "$REPORT_DIR" ] || REPORT_DIR="$ROOT_DIR/runtime_reports/phase47_full_regression_$(date -u +%Y%m%dT%H%M%SZ)"
case "$REPORT_DIR" in /*) ;; *) REPORT_DIR="$ROOT_DIR/$REPORT_DIR" ;; esac
CASES_DIR="$REPORT_DIR/cases"
ARTIFACTS_DIR="$REPORT_DIR/artifacts"
mkdir -p "$CASES_DIR" "$REPORT_DIR/environment" "$ARTIFACTS_DIR" "$REPORT_DIR/failures"
LOG_FILE="$REPORT_DIR/phase47.log"
CASE_FILE="$REPORT_DIR/cases.jsonl"
SUMMARY_JSON="$REPORT_DIR/summary.json"
MATRIX_JSON="$REPORT_DIR/regression_matrix.json"
: > "$LOG_FILE"
: > "$CASE_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1
PYTHON_BIN="$PYTHON_BIN"
TOKEN_FILE="$ROOT_DIR/logs/operator.token"
TOKEN=""
OVERALL=PASS
FIRST=""
SUMMARY_PYTHON="$(command -v python3)"

run_case() {
  name="$1"; shift
  out="$CASES_DIR/$name.stdout"
  err="$CASES_DIR/$name.stderr"
  begin="$(date +%s%N)"
  printf 'CASE_START %s\n' "$name"
  if [ "$VERBOSE" -eq 1 ]; then "$@" > >(tee "$out") 2> >(tee "$err" >&2); rc=$?
  else "$@" > "$out" 2> "$err"; rc=$?
  fi
  end="$(date +%s%N)"
  seconds="$("$SUMMARY_PYTHON" -c 'import sys; print((int(sys.argv[2])-int(sys.argv[1]))/1000000000)' "$begin" "$end")"
  status=PASS
  [ "$rc" -eq 0 ] || status=FAIL
  NAME="$name" STATUS="$status" RC="$rc" SECONDS="$seconds" COMMAND="$*" "$SUMMARY_PYTHON" - "$CASE_FILE" <<'PY'
import json, os, sys
with open(sys.argv[1], "a", encoding="utf-8") as f:
    f.write(json.dumps({"case": os.environ["NAME"], "status": os.environ["STATUS"], "exit_code": int(os.environ["RC"]), "duration_seconds": float(os.environ["SECONDS"]), "command": os.environ["COMMAND"]}) + "\n")
PY
  printf '%-7s %s exit=%s\n' "$status" "$name" "$rc"
  if [ "$status" != PASS ]; then
    [ -n "$FIRST" ] || FIRST="$name"
    OVERALL=FAIL
  fi
  return "$rc"
}
record_blocked() {
  name="$1"; reason="$2"; command="$3"
  printf '%s\n' "CASE_BLOCKED $name reason=$reason"
  NAME="$name" STATUS=BLOCKED RC=3 SECONDS=0 COMMAND="$command" "$SUMMARY_PYTHON" - "$CASE_FILE" <<'PY'
import json, os, sys
with open(sys.argv[1], "a", encoding="utf-8") as f:
    f.write(json.dumps({"case": os.environ["NAME"], "status": os.environ["STATUS"],
                        "exit_code": int(os.environ["RC"]), "duration_seconds": 0.0,
                        "command": os.environ["COMMAND"]}) + "\n")
PY
  [ -n "$FIRST" ] || FIRST="$name"
  OVERALL=BLOCKED
  return 3
}
run_root() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo -n -E "$@"; fi; }
read_token() { [ -s "$TOKEN_FILE" ] && TOKEN="$(cat "$TOKEN_FILE")"; }
api_post() { curl -fsS --max-time 90 -X POST -H 'Content-Type: application/json' -H "X-CCH-Operator-Token: $TOKEN" --data "$2" "http://127.0.0.1:8000$1" > "$3"; }
json_field() { "$PYTHON_BIN" - "$1" "$2" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
for part in sys.argv[2].split("."):
    value = value[part]
print(value)
PY
}
json_expect() {
  "$PYTHON_BIN" - "$1" "$2" "$3" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
for part in sys.argv[2].split("."):
    value = value[part]
if str(value) != sys.argv[3]:
    raise SystemExit(f"expected {sys.argv[2]}={sys.argv[3]!r}, got {value!r}")
PY
}
group_a() {
  run_case A01_remote git -C "$ROOT_DIR" remote get-url origin
  run_case A02_branch bash -c 'test "$(git -C "$1" branch --show-current)" = feature/phase47-full-regression' _ "$ROOT_DIR"
  run_case A03_worktree_scope bash -c 'git -C "$1" status --porcelain | awk "{print substr(\$0,4)}" | grep -Ev "^(docs/phase47_regression_matrix.md|scripts/phase44_firewall_runtime_check.py|scripts/phase47_full_regression_gate.sh|tests/test_phase47_full_regression.py)$" | grep -q . && exit 1 || exit 0' _ "$ROOT_DIR"
  run_case A04_sync bash -c 'test "$(git -C "$1" rev-parse HEAD)" = "$(git -C "$1" rev-parse origin/feature/phase47-full-regression)"' _ "$ROOT_DIR"
  run_case A05_phase44_45 git -C "$ROOT_DIR" merge-base --is-ancestor 15c555f origin/main
  run_case A06_phase46 git -C "$ROOT_DIR" merge-base --is-ancestor origin/feature/phase46-automation-docs origin/main
  run_case A07_sudo sudo -n id
  run_case A08_diff git -C "$ROOT_DIR" diff --check
  run_case A09_no_runtime bash -c 'test -z "$(git -C "$1" ls-files | grep -E "(^|/)(runtime_reports|logs|\\.venv|node_modules)/|\\.pid$|\\.sock$|operator\\.token$|\\.pem$|\\.key$")"' _ "$ROOT_DIR"
}
group_b() {
  run_case B01_validate "$PYTHON_BIN" scripts/validate_vars.py
  run_case B02_verify "$PYTHON_BIN" scripts/verify_network.py
  run_case B03_generate "$PYTHON_BIN" scripts/generate_configs.py
  run_case B04_no_drift git -C "$ROOT_DIR" diff --exit-code -- generated_configs
  run_case B05_source_tests "$PYTHON_BIN" -m pytest -q tests/test_phase41_dual_branch_source.py tests/test_topology_model.py tests/test_user_count.py
  run_case B06_policy_tests "$PYTHON_BIN" -m pytest -q tests/test_phase43_sdn_policy.py tests/test_sdn_policy.py
}
group_c() {
  if find "$ROOT_DIR/scripts" "$ROOT_DIR/sdn_mpls_demo" "$ROOT_DIR/dashboard/backend" -type f -name '*.py' ! -path '*/.venv/*' -print0 | xargs -0 "$PYTHON_BIN" -m py_compile; then
    run_case C01_python_syntax true
  else
    run_case C01_python_syntax false
  fi
  while IFS= read -r file; do run_case C02_$(basename "$file") bash -n "$file"; done < <(find "$ROOT_DIR/scripts" "$ROOT_DIR/sdn_mpls_demo" -maxdepth 1 -name '*.sh' -type f)
  run_case C03_collect "$PYTHON_BIN" -m pytest --collect-only -q
  run_case C04_dashboard "$PYTHON_BIN" -m pytest -q tests/test_dashboard_api.py tests/test_dashboard_health_api.py tests/test_dashboard_iperf_api.py
  run_case C05_transport "$PYTHON_BIN" -m pytest -q tests/test_mininet_control_transport.py tests/test_mininet_control_timeouts.py tests/test_iperf_agent_runtime_contract.py
  run_case C06_full_pytest "$PYTHON_BIN" -m pytest -q
  run_case C07_phase46 "$PYTHON_BIN" -m pytest -q tests/test_phase46_automation_docs.py
  run_case C08_diff git -C "$ROOT_DIR" diff --check
}
group_d() {
  run_case D01_npm_ci npm ci --prefix "$ROOT_DIR/dashboard/frontend"
  run_case D02_frontend_test npm run test --prefix "$ROOT_DIR/dashboard/frontend"
  run_case D03_typecheck npm run typecheck --prefix "$ROOT_DIR/dashboard/frontend"
  run_case D04_build npm run build --prefix "$ROOT_DIR/dashboard/frontend"
  run_case D05_lockfile git -C "$ROOT_DIR" diff --exit-code -- dashboard/frontend/package-lock.json
}
group_e() {
  run_case E01_phase46 run_root bash "$ROOT_DIR/scripts/phase46_automation_docs_gate.sh" all --reuse-running
}
group_f() {
  run_case F01_controller bash -c 'ss -ltn | grep -Eq ":6653[[:space:]]"'
  run_case F02_backend bash -c 'ss -ltn | grep -Eq ":8000[[:space:]]"'
  run_case F03_frontend bash -c 'ss -ltn | grep -Eq ":5173[[:space:]]"'
  run_case F04_topology pgrep -f '[t]opology_hybrid_sdn.py'
  run_case F05_ovs bash -c 'test "$(sudo -n ovs-vsctl list-br | wc -l)" = 9'
  run_case F06_firewalls bash -c 'sudo -n ip netns list | grep -q fw_hq && sudo -n ip netns list | grep -q fw_telesale'
  run_case F07_health curl -fsS http://127.0.0.1:8000/api/health
}
group_g() {
  for switch in access_bo access_hq_a access_hq_b access_hq_c access_hq_it access_telesale core_hq dist_telesale voice_access; do
    run_case G01_$switch bash -c 'sudo -n ovs-ofctl -O OpenFlow13 dump-flows "$1" | tee "$2" | grep -q actions=' _ "$switch" "$ARTIFACTS_DIR/flows_$switch.txt"
  done
  read_token
  api_post /api/test/ping '{"source":"h30_01","destination":"h90"}' "$ARTIFACTS_DIR/ping_allow.json"
  run_case G02_ping_allow json_expect "$ARTIFACTS_DIR/ping_allow.json" decision.action allow
  api_post /api/test/ping '{"source":"h20_01","destination":"h30_01"}' "$ARTIFACTS_DIR/ping_deny.json"
  run_case G03_ping_deny json_expect "$ARTIFACTS_DIR/ping_deny.json" error_code POLICY_DENIED
}
group_h() {
  run_case H01_firewall run_root "$PYTHON_BIN" scripts/phase44_firewall_runtime_check.py
  run_case H02_hq_rules bash -c 'sudo -n ip netns exec fw_hq nft list table inet cch_filter | grep -q social'
  run_case H03_telesale_rules bash -c 'sudo -n ip netns exec fw_telesale nft list table inet cch_filter | grep -q social'
}
group_i() {
  run_case I01_health curl -fsS http://127.0.0.1:8000/api/health
  run_case I02_live_status curl -fsS http://127.0.0.1:8000/api/live/status
  run_case I03_topology curl -fsS http://127.0.0.1:8000/api/topology
  run_case I04_firewalls curl -fsS http://127.0.0.1:8000/api/firewalls
  read_token
  run_case I05_auth bash -c 'curl -fsS -H "X-CCH-Operator-Token: $1" http://127.0.0.1:8000/api/auth/verify' _ "$TOKEN"
}
group_j() {
  run_case J01_dashboard_smoke run_root "$PYTHON_BIN" scripts/dashboard_runtime_smoke_test.py
  run_case J02_smoke_report bash -c 'find "$1" -maxdepth 1 -name "dashboard_runtime_*.json" -print | grep -q . ' _ "$ROOT_DIR/runtime_reports"
}
group_k() {
  read_token
  api_post /api/link/fail '{"link_id":"access_hq_a-core_hq"}' "$ARTIFACTS_DIR/link_fail.json"
  run_case K01_link_down json_expect "$ARTIFACTS_DIR/link_fail.json" status down
  api_post /api/link/recover '{"link_id":"access_hq_a-core_hq"}' "$ARTIFACTS_DIR/link_recover.json"
  run_case K02_link_up json_expect "$ARTIFACTS_DIR/link_recover.json" status up
  run_case K03_no_iperf bash -c '! pgrep -af "[i]perf3"'
}
group_l() {
  run_case L01_backend_count bash -c 'test "$(pgrep -fc "[u]vicorn app.main")" = 1'
  run_case L02_frontend_count bash -c 'test "$(ps -eo args= | awk '\''/\/node_modules\/\.bin\/vite --host/ {count++} END {print count+0}'\'')" = 1'
  run_case L03_controller_count bash -c 'test "$(pgrep -fc "[o]sken-manager")" = 1'
  run_case L04_iperf_count bash -c '! pgrep -af "[i]perf3"'
}
group_m() {
  run_case M01_matrix test -s "$ROOT_DIR/docs/phase47_regression_matrix.md"
  run_case M02_gate test -x "$ROOT_DIR/scripts/phase47_full_regression_gate.sh"
  run_case M03_test "$PYTHON_BIN" -m pytest -q tests/test_phase47_full_regression.py
}
run_group() {
  letter="$1"; function="$2"
  start_lines="$(wc -l < "$CASE_FILE")"
  "$function" || true
  end_lines="$(wc -l < "$CASE_FILE")"
  if [ -z "$CASE_FILTER" ] || [[ "$CASE_FILTER" = "$letter"* ]]; then
    if "$SUMMARY_PYTHON" - "$CASE_FILE" "$start_lines" "$end_lines" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    lines = f.read().splitlines()
subset = [json.loads(line) for line in lines[int(sys.argv[2]):int(sys.argv[3])] if line.strip()]
raise SystemExit(0 if subset and all(item["status"] == "PASS" for item in subset) else 1)
PY
    then run_case "$letter"_GROUP true
    else run_case "$letter"_GROUP false
    fi
  fi
}
run_group_for_mode() {
  [ -z "$CASE_FILTER" ] || [[ "$CASE_FILTER" = "$1"* ]] || return 0
  case "$1" in
    A) run_group A group_a ;;
    B) run_group B group_b ;;
    C) run_group C group_c ;;
    D) run_group D group_d ;;
    E) run_group E group_e ;;
    F) run_group F group_f ;;
    G) run_group G group_g ;;
    H) run_group H group_h ;;
    I) run_group I group_i ;;
    J) run_group J group_j ;;
    K) run_group K group_k ;;
    L) run_group L group_l ;;
    M) run_group M group_m ;;
  esac
}
case "$MODE" in
  preflight) run_group_for_mode A ;;
  source) run_group_for_mode B ;;
  static) run_group_for_mode C ;;
  frontend) run_group_for_mode D ;;
  automation) run_group_for_mode E ;;
  runtime)
    [ "$REUSE_RUNNING" -eq 1 ] || [ "$START_MISSING" -eq 1 ] || record_blocked F_RUNTIME_MODE REUSE_OR_START_REQUIRED "--reuse-running or --start-missing"
    { [ "$REUSE_RUNNING" -eq 1 ] || [ "$START_MISSING" -eq 1 ]; } && for x in F G H I J K L; do run_group_for_mode "$x"; done
    ;;
  full)
    for x in A B C D E; do run_group_for_mode "$x"; done
    [ "$REUSE_RUNNING" -eq 1 ] || [ "$START_MISSING" -eq 1 ] || record_blocked F_RUNTIME_MODE REUSE_OR_START_REQUIRED "--reuse-running or --start-missing"
    { [ "$REUSE_RUNNING" -eq 1 ] || [ "$START_MISSING" -eq 1 ]; } && for x in F G H I J K L; do run_group_for_mode "$x"; done
    run_group_for_mode M
    ;;
esac
{
  uname -a
  id
  "$PYTHON_BIN" --version
  git -C "$ROOT_DIR" status --short --branch
  git -C "$ROOT_DIR" rev-parse HEAD
  git -C "$ROOT_DIR" rev-parse origin/main
  ss -ltnp 2>/dev/null || true
  sudo -n ovs-vsctl list-br 2>/dev/null || true
  sudo -n ip netns list 2>/dev/null || true
} > "$REPORT_DIR/environment/environment.log"
git -C "$ROOT_DIR" status --short > "$REPORT_DIR/files_changed.txt" || true
git -C "$ROOT_DIR" diff --check > "$REPORT_DIR/git_diff_check.log" 2>&1 || true
if [ ! -s "$REPORT_DIR/git_diff_check.log" ]; then printf '%s\n' 'PASS git diff --check' > "$REPORT_DIR/git_diff_check.log"; fi
git -C "$ROOT_DIR" diff --stat > "$REPORT_DIR/git_diff_stat.txt" || true
git -C "$ROOT_DIR" diff > "$REPORT_DIR/git_diff.patch" || true
git -C "$ROOT_DIR" grep -IEn 'BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|Authorization: Bearer' -- . > "$REPORT_DIR/secret_scan.log" 2>&1 || true
if [ ! -s "$REPORT_DIR/secret_scan.log" ]; then printf '%s\n' 'PASS no tracked secret pattern findings' > "$REPORT_DIR/secret_scan.log"; fi
cp "$ROOT_DIR/docs/phase47_regression_matrix.md" "$REPORT_DIR/test_inventory.md"
printf '%s\n' "Git/source cases" > "$REPORT_DIR/baseline.log"
grep -E '"case": "A|_GROUP' "$CASE_FILE" >> "$REPORT_DIR/baseline.log" || true
for spec in \
  "B static_validation.log" \
  "C static_validation.log" \
  "D frontend_validation.log" \
  "E automation_regression.log" \
  "F runtime_inventory.log" \
  "G sdn_policy_regression.log" \
  "H firewall_regression.log" \
  "I dashboard_regression.log" \
  "J traffic_regression.log" \
  "K traffic_regression.log" \
  "L traffic_regression.log"; do
  set -- $spec
  grep -E "\\\"case\\\": \\\"$1|$1_GROUP" "$CASE_FILE" >> "$REPORT_DIR/$2" || true
done
cp "$REPORT_DIR/phase47.log" "$REPORT_DIR/phase47_gate.log"
PHASE46_REPORT="$(ls -td "$ROOT_DIR"/runtime_reports/phase46_automation_docs_* 2>/dev/null | head -1 || true)"
if [ -n "$PHASE46_REPORT" ]; then
  [ -f "$PHASE46_REPORT/phase44_45_regression.log" ] && cp "$PHASE46_REPORT/phase44_45_regression.log" "$REPORT_DIR/phase44_45_acceptance.log"
  [ -f "$PHASE46_REPORT/runtime_validation.log" ] && cp "$PHASE46_REPORT/runtime_validation.log" "$REPORT_DIR/phase46_acceptance.log"
fi
if [ "$OVERALL" = PASS ]; then
  printf '%s\n' 'Phase 47 full regression PASS. No blocking action remains.' > "$REPORT_DIR/NEXT_ACTION.md"
else
  printf '%s\n' 'Phase 47 full regression did not PASS. Review phase47.log and failures before rerun.' > "$REPORT_DIR/NEXT_ACTION.md"
fi
"$SUMMARY_PYTHON" - "$CASE_FILE" "$SUMMARY_JSON" "$MATRIX_JSON" "$ROOT_DIR" "$REPORT_DIR" <<'PY'
import json, re, subprocess, sys
from pathlib import Path
case_file, summary_file, matrix_file, root, report = map(Path, sys.argv[1:])
cases = [json.loads(line) for line in case_file.read_text().splitlines() if line.strip()]
groups = {x["case"].split("_", 1)[0]: x["status"] for x in cases if x["case"].endswith("_GROUP")}
rows = []
for line in (root / "docs/phase47_regression_matrix.md").read_text().splitlines():
    if not line.startswith("|") or "Case ID" in line or line.startswith("|---"):
        continue
    fields = [x.strip() for x in line.strip("|").split("|")]
    if len(fields) >= 6 and re.match(r"^[A-Z][0-9]{2}$", fields[0]):
        rows.append({"case_id": fields[0], "layer": fields[1], "requirement": fields[2], "command_test": fields[4], "expected": fields[5], "status": groups.get(fields[0][0], "BLOCKED"), "evidence": str(report / "cases")})
matrix = {"phase": 47, "overall_status": "PASS" if rows and all(x["status"] == "PASS" for x in rows) else "FAIL", "case_counts": {"total": len(rows), "pass": sum(x["status"] == "PASS" for x in rows), "fail": sum(x["status"] == "FAIL" for x in rows), "blocked": sum(x["status"] == "BLOCKED" for x in rows)}, "cases": rows}
matrix_file.write_text(json.dumps(matrix, indent=2) + "\n")
counts = {status: sum(item["status"] == status for item in cases) for status in ("PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE")}
first_failure = next((item for item in cases if item["status"] != "PASS"), None)
overall_status = "PASS" if matrix["overall_status"] == "PASS" and first_failure is None else ("BLOCKED" if any(item["status"] == "BLOCKED" for item in cases) else "FAIL")
summary = {
    "phase": 47,
    "overall_status": overall_status,
    "branch": subprocess.run(["git", "branch", "--show-current"], cwd=root, capture_output=True, text=True).stdout.strip(),
    "head": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip(),
    "origin_main": subprocess.run(["git", "rev-parse", "--short", "origin/main"], cwd=root, capture_output=True, text=True).stdout.strip(),
    "phase46_verified": subprocess.run(["git", "merge-base", "--is-ancestor", "origin/feature/phase46-automation-docs", "origin/main"], cwd=root).returncode == 0,
    "working_tree_clean_before": not subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout.strip(),
    "case_counts": {"total": len(cases), "pass": counts["PASS"], "fail": counts["FAIL"], "blocked": counts["BLOCKED"], "not_applicable": counts["NOT_APPLICABLE"]},
    "first_failure": first_failure,
    "failure_classification": None if first_failure is None else "MANDATORY_REGRESSION_CASE",
    "fixes": ["Phase 47 controlled worktree checkpoint scope", "Phase 47 gate group aggregation and live process checks"],
    "tests_added": ["tests/test_phase47_full_regression.py"],
    "phase44_45_regression": {"status": groups.get("H", "BLOCKED")},
    "phase46_regression": {"status": groups.get("E", "BLOCKED")},
    "runtime": {"status": "PASS" if all(groups.get(letter) == "PASS" for letter in "FGHIJKL") else "FAIL"},
    "cases": cases,
    "artifacts": [str(x) for x in report.glob("**/*") if x.is_file()] + [str(report / "summary.json")],
    "remaining_risks": [] if first_failure is None else ["Review first failing case and failure bundle."],
}
summary_file.write_text(json.dumps(summary, indent=2) + "\n")
PY
cp "$ROOT_DIR/docs/phase47_regression_matrix.md" "$REPORT_DIR/regression_matrix.md"
for name in baseline.log test_inventory.md static_validation.log frontend_validation.log automation_regression.log runtime_inventory.log sdn_policy_regression.log firewall_regression.log dashboard_regression.log traffic_regression.log phase44_45_acceptance.log phase46_acceptance.log phase47_gate.log NEXT_ACTION.md; do
  [ -e "$REPORT_DIR/$name" ] || : > "$REPORT_DIR/$name"
done
grep -E 'CASE|GROUP|FINAL_STATUS|PHASE47' "$LOG_FILE" > "$REPORT_DIR/phase47_gate.log" || true
echo "FINAL_STATUS=$OVERALL"
[ "$OVERALL" = PASS ] && exit 0
exit 1
