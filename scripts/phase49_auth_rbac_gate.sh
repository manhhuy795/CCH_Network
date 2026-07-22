#!/usr/bin/env bash
set -Eeuo pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-preflight}"
shift || true
REUSE_RUNNING=0
START_MISSING=0
VERBOSE=0
REPORT_DIR=""
TEST_ENV_FILE=""
BRANCH_EXPECTED="feature/phase49-auth-rbac"

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --reuse-running) REUSE_RUNNING=1 ;;
    --start-missing) START_MISSING=1 ;;
    --verbose) VERBOSE=1 ;;
    --report-dir) shift; REPORT_DIR="$1" ;;
    --test-env-file) shift; TEST_ENV_FILE="$1" ;;
    --branch) shift; BRANCH_EXPECTED="$1" ;;
    -h|--help) echo "preflight backend frontend security runtime full"; exit 0 ;;
    *) echo "Khong biet tuy chon: $1" >&2; exit 2 ;;
  esac
  shift
done
case "$MODE" in preflight|backend|frontend|security|runtime|full) ;; *) echo "Mode khong hop le" >&2; exit 2 ;; esac

if [[ -z "$REPORT_DIR" ]]; then
  REPORT_DIR="$ROOT_DIR/runtime_reports/phase49_auth_rbac_$(date -u +%Y%m%dT%H%M%SZ)"
fi
case "$REPORT_DIR" in /*) ;; *) REPORT_DIR="$ROOT_DIR/$REPORT_DIR" ;; esac
mkdir -p "$REPORT_DIR"/{environment,commands,logs,artifacts,failures}
LOG_FILE="$REPORT_DIR/phase49.log"
CASE_FILE="$REPORT_DIR/case_results.jsonl"
: > "$LOG_FILE"
: > "$CASE_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
[[ -x "$PYTHON_BIN" ]] || PYTHON_BIN="$(command -v python3 || true)"
TOKEN_FILE="$ROOT_DIR/logs/operator.token"
TOKEN=""
OVERALL=PASS

case_record() {
  local name="$1" status="$2" rc="$3" seconds="$4" code="$5" summary="$6"
  NAME="$name" STATUS="$status" RC="$rc" SECONDS="$seconds" ERROR_CODE="$code" RESPONSE_SUMMARY="$summary" \
    "$PYTHON_BIN" - "$CASE_FILE" <<'PY'
import json, os, sys
with open(sys.argv[1], "a", encoding="utf-8") as handle:
    handle.write(json.dumps({
        "case": os.environ["NAME"],
        "status": os.environ["STATUS"],
        "exit_code": int(os.environ["RC"]),
        "duration_seconds": float(os.environ["SECONDS"]),
        "error_code": None if os.environ["STATUS"] == "PASS" else os.environ["ERROR_CODE"],
        "response_summary": os.environ["RESPONSE_SUMMARY"],
    }, ensure_ascii=False) + "\n")
PY
}

run_case() {
  local name="$1"; shift
  local out="$REPORT_DIR/commands/${name}.stdout"
  local err="$REPORT_DIR/commands/${name}.stderr"
  local started ended rc status seconds
  started="$(date +%s%N)"
  set +e
  if [[ "$VERBOSE" -eq 1 ]]; then
    "$@" > >(tee "$out") 2> >(tee "$err" >&2); rc=$?
  else
    "$@" > "$out" 2> "$err"; rc=$?
  fi
  set -e
  ended="$(date +%s%N)"
  seconds="$($PYTHON_BIN -c 'import sys; print(round((int(sys.argv[2])-int(sys.argv[1]))/1_000_000_000,3))' "$started" "$ended")"
  status=PASS
  [[ "$rc" -eq 0 ]] || status=FAIL
  [[ "$status" == PASS ]] || OVERALL=FAIL
  case_record "$name" "$status" "$rc" "$seconds" "COMMAND_FAILED" "command=$*"
  printf '%-7s %s exit=%s\n' "$status" "$name" "$rc"
  return 0
}

blocked_case() {
  local name="$1" code="$2" reason="$3"
  printf '%s\n' "$reason" > "$REPORT_DIR/commands/${name}.stdout"
  : > "$REPORT_DIR/commands/${name}.stderr"
  case_record "$name" BLOCKED 3 0 "$code" "$reason"
  OVERALL=BLOCKED
  printf 'BLOCKED %s reason=%s\n' "$name" "$code"
}

read_operator_token() {
  if [[ -s "$TOKEN_FILE" ]]; then
    TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
    [[ "$TOKEN" != *$'\n'* && "$TOKEN" != *$'\r'* ]]
    return 0
  fi
  return 1
}

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo -n "$@"; fi
}

http_expect() {
  local expected="$1" output="$2"; shift 2
  local actual
  actual="$(curl -sS --max-time 90 -o "$output" -w '%{http_code}' "$@" || true)"
  [[ "$actual" == "$expected" ]] || { printf 'expected_http=%s actual_http=%s\n' "$expected" "$actual"; return 1; }
  printf 'http_status=%s\n' "$actual"
}

api_get_operator() {
  local path="$1" output="$2"
  curl -sS --max-time 30 -H "X-CCH-Operator-Token: $TOKEN" -o "$output" "http://127.0.0.1:8000${path}"
}

api_post_operator() {
  local path="$1" body="$2" output="$3"
  printf '%s' "$body" | curl -sS --max-time 90 -X POST -H 'Content-Type: application/json' -H "X-CCH-Operator-Token: $TOKEN" --data-binary @- -o "$output" "http://127.0.0.1:8000${path}"
}

preflight_checks() {
  run_case P01_linux test "$(uname -s)" = Linux
  run_case P02_branch bash -c 'test "$(git -C "$1" branch --show-current)" = "$2"' _ "$ROOT_DIR" "$BRANCH_EXPECTED"
  run_case P03_scope bash -c 'git -C "$1" status --porcelain | awk "{print substr(\$0,4)}" | grep -Ev "^(README\\.md|dashboard/backend/app/(api|auth_store|errors|main|models|security)\\.py|dashboard/frontend/src/(App\\.tsx|api/client\\.ts|components/LoginPanel\\.tsx|components/layout/AppShell(\\.tsx|\\.test\\.tsx)|styles/global\\.css)|scripts/(start_demo\\.sh|phase44_45_combined_acceptance\\.sh|phase44_firewall_runtime_check\\.py|phase49_bootstrap_admin\\.py|phase49_auth_rbac_gate\\.sh|phase49_detailed_status_event_test\\.py|phase49_secret_scan\\.py)|docs/phase49_.*\\.md|tests/(test_dashboard_api\\.py|test_dashboard_health_api\\.py|test_phase49_auth_rbac\\.py))$" | grep -q . && exit 1 || exit 0' _ "$ROOT_DIR"
  run_case P04_main_phase48 bash -c 'git -C "$1" cat-file -e origin/main:scripts/phase48_final_ubuntu_acceptance.sh && git -C "$1" cat-file -e origin/main:docs/phase48_final_acceptance_runbook.md' _ "$ROOT_DIR"
  run_case P05_python "$PYTHON_BIN" --version
  run_case P06_node node --version
  run_case P07_npm npm --version
  run_case P08_required_files bash -c 'for f in dashboard/backend/app/auth_store.py scripts/phase49_bootstrap_admin.py scripts/phase49_detailed_status_event_test.py scripts/phase49_secret_scan.py docs/phase49_authentication_design.md docs/phase49_rbac_matrix.md docs/phase49_security_operations.md docs/phase49_security_test_matrix.md README.md; do test -f "$1/$f" || exit 1; done' _ "$ROOT_DIR"
  run_case P09_diff_check git -C "$ROOT_DIR" diff --check
  git -C "$ROOT_DIR" status --short --branch > "$REPORT_DIR/environment/git_status.txt"
  git -C "$ROOT_DIR" log -20 --oneline > "$REPORT_DIR/environment/git_log.txt"
  git -C "$ROOT_DIR" remote -v > "$REPORT_DIR/environment/git_remote.txt"
}

backend_checks() {
  run_case B01_compile "$PYTHON_BIN" -m py_compile dashboard/backend/app/*.py scripts/phase49_bootstrap_admin.py scripts/phase49_detailed_status_event_test.py
  run_case B02_auth_tests "$PYTHON_BIN" -m pytest -q tests/test_phase49_auth_rbac.py
  run_case B03_dashboard_api "$PYTHON_BIN" -m pytest -q tests/test_dashboard_api.py tests/test_dashboard_health_api.py
  run_case B04_full_pytest "$PYTHON_BIN" -m pytest -q
  run_case B05_bash_syntax bash -c 'find scripts sdn_mpls_demo -maxdepth 2 -type f -name "*.sh" -print0 | xargs -0 -r -n1 bash -n'
}

frontend_checks() {
  run_case F01_typecheck npm run typecheck --prefix "$ROOT_DIR/dashboard/frontend"
  run_case F02_test npm run test --prefix "$ROOT_DIR/dashboard/frontend" -- --run
  run_case F03_build npm run build --prefix "$ROOT_DIR/dashboard/frontend" -- --outDir "$REPORT_DIR/artifacts/frontend-dist"
}

security_checks() {
  run_case S01_secret_scan "$PYTHON_BIN" scripts/phase49_secret_scan.py "$ROOT_DIR"
  run_case S02_bootstrap_help "$PYTHON_BIN" scripts/phase49_bootstrap_admin.py --help
  run_case S03_frontend_token_scan bash -c '! grep -RIn --exclude-dir=node_modules --exclude-dir=dist -E "localStorage|X-CCH-Operator-Token|Authorization.*Bearer" "$1/dashboard/frontend/src"' _ "$ROOT_DIR"
  run_case S04_csrf_source grep -q 'X-CCH-CSRF' "$ROOT_DIR/dashboard/frontend/src/api/client.ts"
  run_case S05_cookie_source grep -q 'httponly=True' "$ROOT_DIR/dashboard/backend/app/api.py"
}

runtime_auth_cases() {
  local run_id="$(date -u +%Y%m%d%H%M%S)_$$"
  local admin_user="phase49gate_${run_id}"
  local admin_password viewer_user viewer_password
  local admin_cookie="/tmp/cch_phase49_admin_${run_id}.cookie"
  local viewer_cookie="/tmp/cch_phase49_viewer_${run_id}.cookie"
  local admin_login="$REPORT_DIR/artifacts/admin_login.json"
  local viewer_login="$REPORT_DIR/artifacts/viewer_login.json"
  admin_password="$($PYTHON_BIN -c 'import secrets; print(secrets.token_urlsafe(24))')"
  viewer_user="p49v_${run_id}"
  viewer_password="$($PYTHON_BIN -c 'import secrets; print(secrets.token_urlsafe(24))')"

  printf '%s\n' "$admin_password" | run_case R07_bootstrap_admin "$PYTHON_BIN" scripts/phase49_bootstrap_admin.py --username "$admin_user" --password-stdin
  printf '%s' "{\"username\":\"$admin_user\",\"password\":\"$admin_password\"}" | curl -sS --max-time 30 -c "$admin_cookie" -b "$admin_cookie" -H 'Content-Type: application/json' --data-binary @- -o "$admin_login" http://127.0.0.1:8000/api/auth/login
  run_case R08_admin_login grep -q '"ok":true' "$admin_login"
  local admin_csrf
  admin_csrf="$(awk '$6 == "cch_csrf" {print $7}' "$admin_cookie" | tail -1)"
  printf '%s' "{\"username\":\"$viewer_user\",\"password\":\"$viewer_password\",\"role\":\"viewer\"}" | curl -sS --max-time 30 -X POST -b "$admin_cookie" -H "X-CCH-CSRF: $admin_csrf" -H 'Content-Type: application/json' --data-binary @- -o "$REPORT_DIR/artifacts/create_viewer.json" http://127.0.0.1:8000/api/admin/users
  printf '%s' "{\"username\":\"$viewer_user\",\"password\":\"$viewer_password\"}" | curl -sS --max-time 30 -c "$viewer_cookie" -b "$viewer_cookie" -H 'Content-Type: application/json' --data-binary @- -o "$viewer_login" http://127.0.0.1:8000/api/auth/login
  run_case R09_viewer_login grep -q '"ok":true' "$viewer_login"
  local viewer_csrf
  viewer_csrf="$(awk '$6 == "cch_csrf" {print $7}' "$viewer_cookie" | tail -1)"
  run_case R10_viewer_runtime_forbidden http_expect 403 "$REPORT_DIR/artifacts/viewer_ping.json" -X POST -b "$viewer_cookie" -H "X-CCH-CSRF: $viewer_csrf" -H 'Content-Type: application/json' --data '{"source":"h20_01","destination":"h90"}' http://127.0.0.1:8000/api/test/ping
  run_case R11_viewer_admin_forbidden http_expect 403 "$REPORT_DIR/artifacts/viewer_admin.json" -b "$viewer_cookie" http://127.0.0.1:8000/api/admin/users
  run_case R12_operator_not_admin http_expect 403 "$REPORT_DIR/artifacts/operator_admin.json" -H "X-CCH-Operator-Token: $TOKEN" http://127.0.0.1:8000/api/admin/users
}

runtime_checks() {
  run_case R01_ports bash -c 'ss -ltn | grep -Eq ":6653[[:space:]]" && ss -ltn | grep -Eq ":8000[[:space:]]" && ss -ltn | grep -Eq ":5173[[:space:]]"'
  run_case R02_topology pgrep -f '[t]opology_hybrid_sdn.py'
  run_case R03_ovs bash -c 'test "$(sudo -n ovs-vsctl list-br | wc -l)" = 9'
  run_case R04_health curl -fsS --max-time 15 http://127.0.0.1:8000/api/health
  if ! read_operator_token; then
    blocked_case R05_operator_token_missing OPERATOR_TOKEN_MISSING "logs/operator.token khong ton tai; khong doc token tu log output"
    return
  fi
  run_case R05_authenticated_topology api_get_operator /api/topology "$REPORT_DIR/artifacts/topology.json"
  run_case R06_authenticated_flows api_get_operator /api/flows "$REPORT_DIR/artifacts/flows.json"
  api_post_operator /api/test/ping '{"source":"h30_01","destination":"h90"}' "$REPORT_DIR/artifacts/ping_allow.json"
  run_case R13_ping_allow grep -q '"action":"allow"' "$REPORT_DIR/artifacts/ping_allow.json"
  api_post_operator /api/test/ping '{"source":"h20_01","destination":"h30_01"}' "$REPORT_DIR/artifacts/ping_deny.json"
  run_case R14_ping_deny grep -q 'POLICY_DENIED' "$REPORT_DIR/artifacts/ping_deny.json"
  runtime_auth_cases
  run_case R15_phase44_45_acceptance sudo -n -E bash scripts/phase44_45_combined_acceptance.sh
}

write_reports() {
  cp "$CASE_FILE" "$REPORT_DIR/case_results.json"
  "$PYTHON_BIN" - "$CASE_FILE" "$REPORT_DIR/summary.json" "$MODE" "$BRANCH_EXPECTED" <<'PY'
import json, subprocess, sys
case_file, summary_file, mode, branch = sys.argv[1:]
cases = [json.loads(line) for line in open(case_file, encoding="utf-8") if line.strip()]
failed = [case for case in cases if case["status"] != "PASS"]
def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False).stdout.strip()
summary = {
    "phase": 49,
    "suite": "auth_rbac",
    "mode": mode,
    "branch": branch,
    "head": git("rev-parse", "--short", "HEAD"),
    "overall_status": "PASS" if not failed else ("BLOCKED" if any(c["status"] == "BLOCKED" for c in failed) else "FAIL"),
    "case_counts": {status: sum(c["status"] == status for c in cases) for status in ("PASS", "FAIL", "BLOCKED")},
    "cases": cases,
    "secret_policy": "tokens/passwords/cookies are not written to report",
}
json.dump(summary, open(summary_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
  "$PYTHON_BIN" - "$REPORT_DIR/summary.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
raise SystemExit(0 if payload["overall_status"] == "PASS" else 1)
PY
}

preflight_checks
case "$MODE" in
  preflight) ;;
  backend) backend_checks ;;
  frontend) frontend_checks ;;
  security) security_checks ;;
  runtime) runtime_checks ;;
  full) backend_checks; frontend_checks; security_checks; runtime_checks ;;
esac

env | grep -E '^(CCH_AUTH|CCH_DASHBOARD_CORS|CCH_DASHBOARD_OPERATOR_TOKEN)=' | sed -E 's/=.*/=[REDACTED]/' > "$REPORT_DIR/environment/redacted_env.txt" || true
git -C "$ROOT_DIR" grep -IEn 'BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|Authorization:[[:space:]]*Bearer' -- . > "$REPORT_DIR/secret_scan.log" 2>&1 || true
printf 'REPORT_DIR=%s\nOVERALL=%s\n' "$REPORT_DIR" "$OVERALL"
write_reports
[[ "$OVERALL" == PASS ]]
