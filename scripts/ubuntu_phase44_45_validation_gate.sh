#!/usr/bin/env bash

set -u -o pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONUTF8=1

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="${CCH_REPO_ROOT:-$DEFAULT_REPO_ROOT}"
MODE=""
START_DASHBOARD=0
REUSE_RUNNING=0
VERBOSE=0
REPORT_DIR=""
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

OVERALL_STATUS="PASS"
FIRST_FAILURE=""
FIRST_FAILURE_REASON=""
FIRST_FAILURE_COMMAND=""
FAILURE_CLASS=""
SOURCE_PATCH_PRECHECK_STATUS="NOT_RUN"
PREFLIGHT_STATUS="NOT_RUN"
STATIC_STATUS="NOT_RUN"
RUNTIME_STATUS="NOT_RUN"
COMBINED_STATUS="NOT_RUN"
WORKING_TREE_CLEAN="unknown"
BRANCH=""
HEAD=""
PYTHON_BIN=""
TOPOLOGY_RUNNING="false"
CONTROLLER_RUNNING="false"
BACKEND_RUNNING="false"
FRONTEND_RUNNING="false"
OVS_BRIDGE_COUNT="0"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/ubuntu_phase44_45_validation_gate.sh <mode> [options]

Modes:
  preflight   Collect Ubuntu, repository and runtime prerequisites.
  static      Run syntax checks, pytest collection, targeted tests and full pytest.
  runtime     Run deep-debug targeted Ubuntu runtime cases.
  combined    Run Phase 44/45 Combined Acceptance when all gates are satisfied.
  all         Run preflight -> static -> runtime -> combined with gating.

Options:
  --start-dashboard       Start missing Backend/Frontend only through the repository's official start script when a safe dashboard-only mode can be proven.
  --reuse-running         Reuse already-running topology/controller/dashboard services.
  --report-dir <path>     Write artifacts to an explicit report directory.
  --verbose               Stream case stdout/stderr while also recording them.
  -h, --help              Show this help.

Environment:
  CCH_REPO_ROOT           Override repository root. Default: parent of this script's directory.
EOF
}

log() {
  local message="$*"
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$message" | tee -a "$LOG_FILE"
}

sanitize_name() {
  printf '%s' "$1" | tr -cs 'A-Za-z0-9._-' '_'
}

is_true() {
  [[ "$1" == "true" || "$1" == "1" || "$1" == "yes" ]]
}

record_failure() {
  local case_name="$1"
  local reason="$2"
  local command_text="${3:-}"
  if [[ -z "$FIRST_FAILURE" ]]; then
    FIRST_FAILURE="$case_name"
    FIRST_FAILURE_REASON="$reason"
    FIRST_FAILURE_COMMAND="$command_text"
  fi
  if [[ "$OVERALL_STATUS" != "BLOCKED" ]]; then
    OVERALL_STATUS="FAIL"
  fi
}

record_blocked() {
  local case_name="$1"
  local reason="$2"
  local command_text="${3:-}"
  if [[ -z "$FIRST_FAILURE" ]]; then
    FIRST_FAILURE="$case_name"
    FIRST_FAILURE_REASON="$reason"
    FIRST_FAILURE_COMMAND="$command_text"
  fi
  OVERALL_STATUS="BLOCKED"
}

append_case_json() {
  local name="$1" status="$2" exit_code="$3" duration="$4" command_text="$5" stdout_file="$6" stderr_file="$7" reason="$8"
  CASE_NAME="$name" CASE_STATUS="$status" CASE_EXIT_CODE="$exit_code" CASE_DURATION="$duration" CASE_COMMAND="$command_text" CASE_STDOUT="$stdout_file" CASE_STDERR="$stderr_file" CASE_REASON="$reason" \
    "$SUMMARY_PYTHON" - "$CASE_JSONL" <<'PY'
import json, os, sys
path = sys.argv[1]
obj = {
    "case": os.environ["CASE_NAME"],
    "status": os.environ["CASE_STATUS"],
    "exit_code": int(os.environ["CASE_EXIT_CODE"]),
    "duration_seconds": float(os.environ["CASE_DURATION"]),
    "command": os.environ["CASE_COMMAND"],
    "stdout": os.environ["CASE_STDOUT"],
    "stderr": os.environ["CASE_STDERR"],
    "reason": os.environ["CASE_REASON"],
}
with open(path, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(obj, ensure_ascii=False) + "\n")
PY
}

run_case() {
  local name="$1"; shift
  local safe_name stdout_file stderr_file command_text start_ms end_ms duration_ms duration rc status reason
  safe_name="$(sanitize_name "$name")"
  stdout_file="$CASES_DIR/${safe_name}.stdout"
  stderr_file="$CASES_DIR/${safe_name}.stderr"
  printf -v command_text '%q ' "$@"
  command_text="${command_text% }"

  log "CASE_START name=$name command=$command_text"
  start_ms="$(date +%s%3N 2>/dev/null || date +%s000)"
  if (( VERBOSE )); then
    "$@" > >(tee "$stdout_file") 2> >(tee "$stderr_file" >&2)
    rc=$?
  else
    "$@" >"$stdout_file" 2>"$stderr_file"
    rc=$?
  fi
  end_ms="$(date +%s%3N 2>/dev/null || date +%s000)"
  duration_ms=$((end_ms - start_ms))
  duration="$(awk -v ms="$duration_ms" 'BEGIN { printf "%.3f", ms / 1000 }')"
  status="PASS"
  reason=""
  if (( rc != 0 )); then
    status="FAIL"
    reason="EXIT_CODE_${rc}"
  fi
  append_case_json "$name" "$status" "$rc" "$duration" "$command_text" "$stdout_file" "$stderr_file" "$reason"
  log "CASE_END name=$name status=$status exit_code=$rc duration=${duration}s stdout=$stdout_file stderr=$stderr_file"
  return "$rc"
}

run_case_allow_missing() {
  local name="$1"; shift
  if command -v "$1" >/dev/null 2>&1; then
    run_case "$name" "$@"
  else
    local safe_name stdout_file stderr_file
    safe_name="$(sanitize_name "$name")"
    stdout_file="$CASES_DIR/${safe_name}.stdout"
    stderr_file="$CASES_DIR/${safe_name}.stderr"
    printf 'Command not found: %s\n' "$1" >"$stderr_file"
    : >"$stdout_file"
    append_case_json "$name" "BLOCKED" "127" "0.000" "$*" "$stdout_file" "$stderr_file" "MISSING_COMMAND_$1"
    log "CASE_END name=$name status=BLOCKED reason=MISSING_COMMAND_$1"
    return 127
  fi
}

case_passed() {
  local name="$1"
  "$SUMMARY_PYTHON" - "$CASE_JSONL" "$name" <<'PY'
import json, sys
path, wanted = sys.argv[1:]
status = None
try:
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            if item.get("case") == wanted:
                status = item.get("status")
except FileNotFoundError:
    pass
raise SystemExit(0 if status == "PASS" else 1)
PY
}

select_python() {
  local candidate
  for candidate in \
    "$REPO_ROOT/.venv/bin/python" \
    "$REPO_ROOT/dashboard/backend/.venv/bin/python" \
    "$REPO_ROOT/sdn_mpls_demo/.venv/bin/python" \
    "$(command -v python3 2>/dev/null || true)"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      PYTHON_BIN="$candidate"
      return 0
    fi
  done
  return 1
}

refresh_git_state() {
  if [[ ! -d "$REPO_ROOT/.git" ]]; then
    BRANCH=""
    HEAD=""
    WORKING_TREE_CLEAN="unknown"
    return 1
  fi
  BRANCH="$(git -C "$REPO_ROOT" branch --show-current 2>/dev/null || true)"
  HEAD="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || true)"
  if [[ -z "$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null)" ]]; then
    WORKING_TREE_CLEAN="true"
  else
    WORKING_TREE_CLEAN="false"
  fi
  return 0
}

port_listening() {
  local port="$1"
  ss -ltn 2>/dev/null | awk -v p=":$port" '$4 ~ p"$" {found=1} END {exit(found?0:1)}'
}

socket_exists() {
  [[ -S "$1" ]]
}

logical_topology_running() {
  local matches
  matches="$(pgrep -af '[t]opology_hybrid_sdn.py' 2>/dev/null || true)"
  [[ -n "$matches" ]]
}

controller_running() {
  pgrep -af '[o]sken-manager|[c]ontroller_policy.py' >/dev/null 2>&1
}

backend_running() {
  port_listening 8000
}

frontend_running() {
  port_listening 5173
}

ovs_bridge_count() {
  if ! command -v ovs-vsctl >/dev/null 2>&1; then
    printf '0'
    return
  fi
  sudo -n -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 timeout 10 ovs-vsctl list-br 2>/dev/null | sed '/^[[:space:]]*$/d' | wc -l | tr -d ' '
}

runtime_health_snapshot() {
  TOPOLOGY_RUNNING="false"
  CONTROLLER_RUNNING="false"
  BACKEND_RUNNING="false"
  FRONTEND_RUNNING="false"
  logical_topology_running && TOPOLOGY_RUNNING="true"
  controller_running && CONTROLLER_RUNNING="true"
  backend_running && BACKEND_RUNNING="true"
  frontend_running && FRONTEND_RUNNING="true"
  OVS_BRIDGE_COUNT="$(ovs_bridge_count)"
}

source_patch_precheck() {
  SOURCE_PATCH_PRECHECK_STATUS="PASS"
  local deep_debug="$REPO_ROOT/scripts/ubuntu_phase44_45_deep_debug.py"
  local git_test="$REPO_ROOT/tests/test_phase44_git_checkpoint.py"

  if [[ ! -f "$deep_debug" ]]; then
    SOURCE_PATCH_PRECHECK_STATUS="FAIL"
    record_failure "source_patch_deep_debug" "MISSING_scripts/ubuntu_phase44_45_deep_debug.py" "test -f $deep_debug"
    log "SOURCE_PATCH_PRECHECK=FAIL missing=$deep_debug"
    return 1
  fi
  if [[ ! -f "$git_test" ]]; then
    SOURCE_PATCH_PRECHECK_STATUS="FAIL"
    record_failure "source_patch_git_test" "MISSING_tests/test_phase44_git_checkpoint.py" "test -f $git_test"
    log "SOURCE_PATCH_PRECHECK=FAIL missing=$git_test"
    return 1
  fi
  if ! select_python; then
    SOURCE_PATCH_PRECHECK_STATUS="BLOCKED"
    record_blocked "source_patch_python" "NO_USABLE_PYTHON" "select_python"
    log "SOURCE_PATCH_PRECHECK=FAIL reason=NO_USABLE_PYTHON"
    return 1
  fi

  if ! run_case "source_patch_deep_debug_help" "$PYTHON_BIN" "$deep_debug" --help; then
    SOURCE_PATCH_PRECHECK_STATUS="FAIL"
    record_failure "source_patch_deep_debug_help" "DEEP_DEBUG_HELP_FAILED" "$PYTHON_BIN $deep_debug --help"
    return 1
  fi
  local help_file="$CASES_DIR/source_patch_deep_debug_help.stdout"
  local required
  for required in diagnose verify run-case; do
    if ! grep -Fq -- "$required" "$help_file"; then
      SOURCE_PATCH_PRECHECK_STATUS="FAIL"
      record_failure "source_patch_cli_$required" "MISSING_DEEP_DEBUG_CLI_$required" "grep $required $help_file"
      log "SOURCE_PATCH_PRECHECK=FAIL missing_cli=$required"
      return 1
    fi
  done
  if ! run_case "source_patch_deep_debug_run_case_help" "$PYTHON_BIN" "$deep_debug" run-case --help; then
    SOURCE_PATCH_PRECHECK_STATUS="FAIL"
    record_failure "source_patch_deep_debug_run_case_help" "DEEP_DEBUG_RUN_CASE_HELP_FAILED" "$PYTHON_BIN $deep_debug run-case --help"
    return 1
  fi
  help_file="$CASES_DIR/source_patch_deep_debug_run_case_help.stdout"
  for required in firewall-counter git-checkpoint iperf-concurrency; do
    if ! grep -Fq -- "$required" "$help_file"; then
      SOURCE_PATCH_PRECHECK_STATUS="FAIL"
      record_failure "source_patch_cli_$required" "MISSING_DEEP_DEBUG_CLI_$required" "grep $required $help_file"
      log "SOURCE_PATCH_PRECHECK=FAIL missing_cli=$required"
      return 1
    fi
  done

  if ! run_case "source_patch_pytest_collect_git_checkpoint" "$PYTHON_BIN" -m pytest --collect-only -q "$git_test"; then
    SOURCE_PATCH_PRECHECK_STATUS="FAIL"
    record_failure "source_patch_pytest_collect_git_checkpoint" "NEW_TEST_NOT_COLLECTABLE" "$PYTHON_BIN -m pytest --collect-only -q $git_test"
    return 1
  fi
  if ! run_case "source_patch_full_pytest_collection" "$PYTHON_BIN" -m pytest --collect-only -q "$REPO_ROOT"; then
    SOURCE_PATCH_PRECHECK_STATUS="FAIL"
    record_failure "source_patch_full_pytest_collection" "FULL_TEST_COLLECTION_IMPORT_ERROR" "$PYTHON_BIN -m pytest --collect-only -q $REPO_ROOT"
    return 1
  fi

  log "SOURCE_PATCH_PRECHECK=PASS"
  return 0
}

safe_start_dashboard() {
  (( START_DASHBOARD )) || return 0
  runtime_health_snapshot
  if is_true "$BACKEND_RUNNING" && is_true "$FRONTEND_RUNNING"; then
    log "DASHBOARD_START=SKIP reason=ALREADY_RUNNING"
    return 0
  fi
  local start_script="$REPO_ROOT/scripts/start_demo.sh"
  if [[ ! -f "$start_script" ]]; then
    record_blocked "start_dashboard" "OFFICIAL_START_SCRIPT_MISSING" "$start_script"
    return 1
  fi
  cp "$start_script" "$ENV_DIR/start_demo.sh.inspected" 2>/dev/null || true
  run_case "start_demo_help" bash "$start_script" --help || true

  if grep -Eq -- '--dashboard-only|dashboard-only' "$start_script"; then
    log "DASHBOARD_START=ATTEMPT mode=dashboard-only"
    run_case "start_dashboard_official" bash "$start_script" --dashboard-only || {
      record_blocked "start_dashboard_official" "OFFICIAL_DASHBOARD_START_FAILED" "bash $start_script --dashboard-only"
      return 1
    }
  else
    record_blocked "start_dashboard" "OFFICIAL_START_SCRIPT_HAS_NO_PROVEN_DASHBOARD_ONLY_MODE" "$start_script"
    log "DASHBOARD_START=BLOCKED reason=UNSAFE_TO_INFER_START_MODE"
    return 1
  fi
  return 0
}

collect_environment() {
  run_case "env_uname" uname -a || true
  run_case "env_os_release" cat /etc/os-release || true
  run_case "env_id" id || true
  run_case "env_git_status" git -C "$REPO_ROOT" status --porcelain || true
  run_case "env_git_diff_check" git -C "$REPO_ROOT" diff --check || true
  run_case "env_system_python" python3 --version || true
  [[ -x "$REPO_ROOT/.venv/bin/python" ]] && run_case "env_root_venv_python" "$REPO_ROOT/.venv/bin/python" --version || true
  [[ -x "$REPO_ROOT/dashboard/backend/.venv/bin/python" ]] && run_case "env_backend_venv_python" "$REPO_ROOT/dashboard/backend/.venv/bin/python" --version || true
  [[ -x "$REPO_ROOT/sdn_mpls_demo/.venv/bin/python" ]] && run_case "env_sdn_venv_python" "$REPO_ROOT/sdn_mpls_demo/.venv/bin/python" --version || true
  command -v mn >/dev/null 2>&1 && run_case "env_mininet_version" timeout 10 mn --version || true
  command -v ovs-vsctl >/dev/null 2>&1 && run_case "env_ovs_version" timeout 10 ovs-vsctl --version || true
  command -v osken-manager >/dev/null 2>&1 && run_case "env_osken_version" timeout 10 osken-manager --version || true
  command -v nft >/dev/null 2>&1 && run_case "env_nft_version" nft --version || true
  command -v iperf3 >/dev/null 2>&1 && run_case "env_iperf3_version" iperf3 --version || true
  command -v node >/dev/null 2>&1 && run_case "env_node_version" node --version || true
  command -v npm >/dev/null 2>&1 && run_case "env_npm_version" npm --version || true
  run_case "env_processes" bash -lc "pgrep -af '[t]opology_hybrid_sdn.py|[o]sken-manager|[c]ontroller_policy.py|[u]vicorn|[v]ite|[i]perf3' || true" || true
  run_case "env_ports" bash -lc "ss -ltnp 2>/dev/null | grep -E ':(6653|8000|5173)([[:space:]]|$)' || true" || true
}

runtime_preflight_checks() {
  runtime_health_snapshot
  run_case "runtime_topology_process" bash -lc "pgrep -af '[t]opology_hybrid_sdn.py'" || true
  run_case "runtime_controller_process" bash -lc "pgrep -af '[o]sken-manager|[c]ontroller_policy.py'" || true
  run_case "runtime_port_6653" bash -lc "ss -ltn | grep -E '[:.]6653[[:space:]]'" || true
  run_case "runtime_port_8000" bash -lc "ss -ltn | grep -E '[:.]8000[[:space:]]'" || true
  run_case "runtime_port_5173" bash -lc "ss -ltn | grep -E '[:.]5173[[:space:]]'" || true
  command -v ovs-vsctl >/dev/null 2>&1 && run_case "runtime_ovs_bridges" sudo -n -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 timeout 10 ovs-vsctl list-br || true
  command -v ovs-vsctl >/dev/null 2>&1 && run_case "runtime_ovs_controllers" sudo -n -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 timeout 15 bash -lc "for br in \$(ovs-vsctl list-br 2>/dev/null); do echo \"BRIDGE=\$br\"; ovs-vsctl get-controller \"\$br\"; ovs-vsctl get Bridge \"\$br\" fail_mode 2>/dev/null || true; done" || true
  command -v ip >/dev/null 2>&1 && run_case "runtime_namespaces" timeout 10 ip netns list || true
  run_case "runtime_control_socket" bash -lc "stat /tmp/cch_mininet_control.sock" || true
  run_case "runtime_osken_socket" bash -lc "stat /tmp/cch_osken_admin.sock" || true
  command -v curl >/dev/null 2>&1 && run_case "runtime_openapi" curl -fsS --max-time 5 http://127.0.0.1:8000/openapi.json || true
  command -v curl >/dev/null 2>&1 && run_case "runtime_backend_health" curl -fsS --max-time 5 http://127.0.0.1:8000/api/health || true

  if ! is_true "$TOPOLOGY_RUNNING"; then
    PREFLIGHT_STATUS="BLOCKED"
    record_blocked "runtime_topology_process" "TOPOLOGY_NOT_RUNNING" "pgrep -af topology_hybrid_sdn.py"
    log "RUNTIME_PREFLIGHT=BLOCKED REASON=TOPOLOGY_NOT_RUNNING"
    return 1
  fi
  if ! is_true "$CONTROLLER_RUNNING"; then
    PREFLIGHT_STATUS="BLOCKED"
    record_blocked "runtime_controller_process" "CONTROLLER_NOT_RUNNING" "pgrep -af osken-manager"
    return 1
  fi
  if [[ "$OVS_BRIDGE_COUNT" != "9" ]]; then
    PREFLIGHT_STATUS="BLOCKED"
    record_blocked "runtime_ovs_bridges" "OVS_BRIDGE_COUNT_${OVS_BRIDGE_COUNT}_EXPECTED_9" "ovs-vsctl list-br"
    return 1
  fi
  if ! socket_exists /tmp/cch_mininet_control.sock || ! socket_exists /tmp/cch_osken_admin.sock; then
    PREFLIGHT_STATUS="BLOCKED"
    record_blocked "runtime_sockets" "REQUIRED_RUNTIME_SOCKET_MISSING" "stat runtime sockets"
    return 1
  fi
  if ! is_true "$BACKEND_RUNNING" || ! is_true "$FRONTEND_RUNNING"; then
    safe_start_dashboard || return 1
    runtime_health_snapshot
  fi
  if ! is_true "$BACKEND_RUNNING"; then
    PREFLIGHT_STATUS="BLOCKED"
    record_blocked "runtime_backend" "BACKEND_NOT_RUNNING" "port 8000"
    return 1
  fi
  if ! is_true "$FRONTEND_RUNNING"; then
    PREFLIGHT_STATUS="BLOCKED"
    record_blocked "runtime_frontend" "FRONTEND_NOT_RUNNING" "port 5173"
    return 1
  fi
  return 0
}

mode_preflight() {
  PREFLIGHT_STATUS="PASS"
  log "MODE=preflight REPO_ROOT=$REPO_ROOT"
  if [[ ! -d "$REPO_ROOT" ]]; then
    PREFLIGHT_STATUS="BLOCKED"
    record_blocked "repository_path" "REPOSITORY_NOT_FOUND" "$REPO_ROOT"
    log "PREFLIGHT=BLOCKED REASON=REPOSITORY_NOT_FOUND"
    return 1
  fi
  refresh_git_state || {
    PREFLIGHT_STATUS="BLOCKED"
    record_blocked "repository_git" "NOT_A_GIT_REPOSITORY" "git -C $REPO_ROOT status"
    return 1
  }
  collect_environment
  source_patch_precheck || {
    PREFLIGHT_STATUS="FAIL"
    return 1
  }
  runtime_preflight_checks || return 1
  log "PREFLIGHT=PASS"
  return 0
}

static_py_compile_files() {
  local candidates=()
  local path
  for path in \
    scripts/ubuntu_phase44_45_deep_debug.py \
    tests/test_phase44_git_checkpoint.py \
    dashboard/backend/app/live_mininet.py \
    scripts/phase44_firewall_runtime_check.py \
    sdn_mpls_demo/firewall_nftables.py \
    sdn_mpls_demo/topology_hybrid_sdn.py \
    tests/test_iperf_agent_runtime_contract.py \
    tests/test_phase44_firewall.py \
    tests/test_phase45_dashboard_contract.py; do
    [[ -f "$REPO_ROOT/$path" ]] && candidates+=("$REPO_ROOT/$path")
  done
  if (( ${#candidates[@]} == 0 )); then
    return 1
  fi
  run_case "static_python_syntax" "$PYTHON_BIN" -m py_compile "${candidates[@]}"
}

run_test_file_if_exists() {
  local case_name="$1" relative_path="$2"
  if [[ ! -f "$REPO_ROOT/$relative_path" ]]; then
    local out="$CASES_DIR/$(sanitize_name "$case_name").stdout"
    local err="$CASES_DIR/$(sanitize_name "$case_name").stderr"
    : >"$out"
    printf 'Missing test file: %s\n' "$relative_path" >"$err"
    append_case_json "$case_name" "FAIL" "2" "0.000" "test -f $relative_path" "$out" "$err" "MISSING_TEST_FILE"
    return 2
  fi
  run_case "$case_name" "$PYTHON_BIN" -m pytest -q "$REPO_ROOT/$relative_path"
}

mode_static() {
  STATIC_STATUS="PASS"
  log "MODE=static REPO_ROOT=$REPO_ROOT"
  if [[ ! -d "$REPO_ROOT/.git" ]]; then
    STATIC_STATUS="BLOCKED"
    record_blocked "static_repository" "REPOSITORY_NOT_AVAILABLE" "$REPO_ROOT"
    return 1
  fi
  refresh_git_state || true
  source_patch_precheck || {
    STATIC_STATUS="FAIL"
    return 1
  }
  if ! static_py_compile_files; then
    STATIC_STATUS="FAIL"
    record_failure "static_python_syntax" "PYTHON_SYNTAX_CHECK_FAILED" "$PYTHON_BIN -m py_compile ..."
    return 1
  fi
  if ! run_case "static_shell_syntax_gate" bash -n "$REPO_ROOT/scripts/ubuntu_phase44_45_validation_gate.sh"; then
    STATIC_STATUS="FAIL"; record_failure "static_shell_syntax_gate" "SHELL_SYNTAX_FAILED" "bash -n validation_gate"; return 1
  fi
  if ! run_case "static_shell_syntax_bundle" bash -n "$REPO_ROOT/scripts/ubuntu_phase44_45_failure_bundle.sh"; then
    STATIC_STATUS="FAIL"; record_failure "static_shell_syntax_bundle" "SHELL_SYNTAX_FAILED" "bash -n failure_bundle"; return 1
  fi
  if ! run_case "static_pytest_collection" "$PYTHON_BIN" -m pytest --collect-only -q "$REPO_ROOT"; then
    STATIC_STATUS="FAIL"; record_failure "static_pytest_collection" "PYTEST_COLLECTION_FAILED" "$PYTHON_BIN -m pytest --collect-only"; return 1
  fi
  run_test_file_if_exists "static_firewall_parser_tests" "tests/test_phase45_dashboard_contract.py" || {
    STATIC_STATUS="FAIL"; record_failure "static_firewall_parser_tests" "TARGETED_FIREWALL_TESTS_FAILED" "pytest tests/test_phase45_dashboard_contract.py"; return 1
  }
  run_test_file_if_exists "static_git_checkpoint_tests" "tests/test_phase44_git_checkpoint.py" || {
    STATIC_STATUS="FAIL"; record_failure "static_git_checkpoint_tests" "TARGETED_GIT_CHECKPOINT_TESTS_FAILED" "pytest tests/test_phase44_git_checkpoint.py"; return 1
  }
  run_test_file_if_exists "static_iperf_contract_tests" "tests/test_iperf_agent_runtime_contract.py" || {
    STATIC_STATUS="FAIL"; record_failure "static_iperf_contract_tests" "TARGETED_IPERF_TESTS_FAILED" "pytest tests/test_iperf_agent_runtime_contract.py"; return 1
  }
  run_test_file_if_exists "static_phase44_firewall_tests" "tests/test_phase44_firewall.py" || {
    STATIC_STATUS="FAIL"; record_failure "static_phase44_firewall_tests" "PHASE44_TESTS_FAILED" "pytest tests/test_phase44_firewall.py"; return 1
  }
  run_test_file_if_exists "static_phase45_dashboard_tests" "tests/test_phase45_dashboard_contract.py" || {
    STATIC_STATUS="FAIL"; record_failure "static_phase45_dashboard_tests" "PHASE45_TESTS_FAILED" "pytest tests/test_phase45_dashboard_contract.py"; return 1
  }
  if [[ -d "$REPO_ROOT/dashboard/backend/tests" ]]; then
    run_case "static_dashboard_api_tests" "$PYTHON_BIN" -m pytest -q "$REPO_ROOT/dashboard/backend/tests" || {
      STATIC_STATUS="FAIL"; record_failure "static_dashboard_api_tests" "DASHBOARD_API_TESTS_FAILED" "pytest dashboard/backend/tests"; return 1
    }
  else
    log "STATIC dashboard API tests: directory not present; full pytest remains authoritative."
  fi
  if ! run_case "static_full_pytest" "$PYTHON_BIN" -m pytest -q "$REPO_ROOT"; then
    STATIC_STATUS="FAIL"; record_failure "static_full_pytest" "FULL_PYTEST_FAILED" "$PYTHON_BIN -m pytest -q"; return 1
  fi
  if ! run_case "static_git_diff_check" git -C "$REPO_ROOT" diff --check; then
    STATIC_STATUS="FAIL"; record_failure "static_git_diff_check" "GIT_DIFF_CHECK_FAILED" "git diff --check"; return 1
  fi
  log "STATIC_VALIDATION=PASS PYTHON_EXECUTABLE=$PYTHON_BIN"
  return 0
}

snapshot_iperf() {
  pgrep -af '[i]perf3' 2>/dev/null | sort || true
}

post_case_health() {
  local case_name="$1" baseline_iperf="$2"
  runtime_health_snapshot
  local current_iperf new_iperf
  current_iperf="$(snapshot_iperf)"
  new_iperf="$(comm -13 <(printf '%s\n' "$baseline_iperf" | sed '/^$/d' | sort) <(printf '%s\n' "$current_iperf" | sed '/^$/d' | sort) 2>/dev/null || true)"
  {
    printf 'topology=%s\n' "$TOPOLOGY_RUNNING"
    printf 'controller=%s\n' "$CONTROLLER_RUNNING"
    printf 'backend=%s\n' "$BACKEND_RUNNING"
    printf 'frontend=%s\n' "$FRONTEND_RUNNING"
    printf 'ovs_bridge_count=%s\n' "$OVS_BRIDGE_COUNT"
    printf 'new_iperf_processes=%s\n' "$new_iperf"
  } >"$ENV_DIR/post_${case_name}_health.txt"
  if ! is_true "$TOPOLOGY_RUNNING" || ! is_true "$CONTROLLER_RUNNING" || ! is_true "$BACKEND_RUNNING" || [[ "$OVS_BRIDGE_COUNT" != "9" ]] || [[ -n "$new_iperf" ]]; then
    return 1
  fi
  return 0
}

validate_firewall_runtime_output() {
  local file="$1"
  grep -Eq 'raw(_| )?delta[^0-9]*[1-9][0-9]*|"raw_delta"[[:space:]]*:[[:space:]]*[1-9][0-9]*' "$file" &&
  grep -Eq 'api(_| )?delta[^0-9]*[1-9][0-9]*|"api_delta"[[:space:]]*:[[:space:]]*[1-9][0-9]*' "$file" &&
  grep -Eq 'rule_count[^0-9]*13|"rule_count"[[:space:]]*:[[:space:]]*13' "$file" &&
  grep -Eq 'expected_rule_count[^0-9]*13|"expected_rule_count"[[:space:]]*:[[:space:]]*13' "$file" &&
  grep -Eqi 'policy(_| )?action[^a-z]*(deny)|"action"[[:space:]]*:[[:space:]]*"deny"|POLICY_DENIED' "$file" &&
  grep -Eq 'blocked_at[^A-Za-z0-9_]*fw_hq|"blocked_at"[[:space:]]*:[[:space:]]*"fw_hq"' "$file"
}

validate_git_checkpoint_output() {
  local file="$1"
  grep -Eqi 'branch' "$file" && grep -Eqi 'HEAD|head' "$file" && grep -Eqi 'working_tree_clean|clean' "$file" &&
  grep -Eqi 'ancestor' "$file" && grep -Eqi 'allowed.branch|branch.allowed|allowed_branch' "$file" &&
  grep -Eqi 'checkpoint|final' "$file"
}

validate_iperf_output() {
  local file="$1"
  ! grep -Eq 'IPERF_PARSE_FAILED|IPERF_CLIENT_TIMEOUT' "$file" &&
  grep -Eqi 'overlap[^0-9]*[1-9]|"overlap[^\"]*"[[:space:]]*:[[:space:]]*[1-9]' "$file" &&
  grep -Eq '409' "$file" && grep -Eq 'IPERF_BUSY' "$file" &&
  grep -Eqi 'agent.*health|health.*agent' "$file"
}

mode_runtime() {
  RUNTIME_STATUS="PASS"
  log "MODE=runtime REPO_ROOT=$REPO_ROOT"
  if [[ ! -d "$REPO_ROOT/.git" ]]; then
    RUNTIME_STATUS="BLOCKED"; record_blocked "runtime_repository" "REPOSITORY_NOT_AVAILABLE" "$REPO_ROOT"; return 1
  fi
  refresh_git_state || true
  source_patch_precheck || { RUNTIME_STATUS="FAIL"; return 1; }
  runtime_preflight_checks || { RUNTIME_STATUS="BLOCKED"; return 1; }

  local deep_debug="$REPO_ROOT/scripts/ubuntu_phase44_45_deep_debug.py"
  local baseline_iperf combined_out
  baseline_iperf="$(snapshot_iperf)"

  if ! run_case "runtime_diagnose" sudo -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 python3 "$deep_debug" diagnose; then
    RUNTIME_STATUS="FAIL"; record_failure "runtime_diagnose" "DEEP_DEBUG_DIAGNOSE_FAILED" "sudo ... deep_debug.py diagnose"; return 1
  fi
  post_case_health "diagnose" "$baseline_iperf" || { RUNTIME_STATUS="FAIL"; record_failure "post_diagnose_health" "RUNTIME_HEALTH_REGRESSION" "health checks"; return 1; }

  if ! run_case "runtime_firewall_counter" sudo -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 python3 "$deep_debug" run-case firewall-counter; then
    RUNTIME_STATUS="FAIL"; record_failure "runtime_firewall_counter" "FIREWALL_COUNTER_CASE_FAILED" "sudo ... run-case firewall-counter"; return 1
  fi
  combined_out="$CASES_DIR/runtime_firewall_counter.combined"
  cat "$CASES_DIR/runtime_firewall_counter.stdout" "$CASES_DIR/runtime_firewall_counter.stderr" >"$combined_out"
  if ! validate_firewall_runtime_output "$combined_out"; then
    RUNTIME_STATUS="FAIL"; record_failure "runtime_firewall_counter_acceptance" "FIREWALL_RUNTIME_EVIDENCE_INCOMPLETE" "validate firewall evidence"; return 1
  fi
  post_case_health "firewall_counter" "$baseline_iperf" || { RUNTIME_STATUS="FAIL"; record_failure "post_firewall_health" "RUNTIME_HEALTH_REGRESSION" "health checks"; return 1; }

  if ! run_case "runtime_git_checkpoint" sudo -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 python3 "$deep_debug" run-case git-checkpoint; then
    refresh_git_state || true
    if [[ "$WORKING_TREE_CLEAN" == "false" ]]; then
      RUNTIME_STATUS="BLOCKED"
      record_blocked "runtime_git_checkpoint" "VALIDATION_BLOCKED_BY_DIRTY_WORKTREE" "sudo ... run-case git-checkpoint"
      log "COMBINED_ACCEPTANCE_BLOCKED=YES"
      log "ACTION_REQUIRED=Create an explicit local checkpoint commit after user approval"
      return 1
    fi
    RUNTIME_STATUS="FAIL"; record_failure "runtime_git_checkpoint" "GIT_CHECKPOINT_CODE_FAILURE" "sudo ... run-case git-checkpoint"; return 1
  fi
  combined_out="$CASES_DIR/runtime_git_checkpoint.combined"
  cat "$CASES_DIR/runtime_git_checkpoint.stdout" "$CASES_DIR/runtime_git_checkpoint.stderr" >"$combined_out"
  if ! validate_git_checkpoint_output "$combined_out"; then
    RUNTIME_STATUS="FAIL"; record_failure "runtime_git_checkpoint_acceptance" "GIT_CHECKPOINT_EVIDENCE_INCOMPLETE" "validate git checkpoint evidence"; return 1
  fi
  post_case_health "git_checkpoint" "$baseline_iperf" || { RUNTIME_STATUS="FAIL"; record_failure "post_git_checkpoint_health" "RUNTIME_HEALTH_REGRESSION" "health checks"; return 1; }

  if ! run_case "runtime_iperf_concurrency" sudo -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 python3 "$deep_debug" run-case iperf-concurrency; then
    RUNTIME_STATUS="FAIL"; record_failure "runtime_iperf_concurrency" "IPERF_CONCURRENCY_CASE_FAILED" "sudo ... run-case iperf-concurrency"; return 1
  fi
  combined_out="$CASES_DIR/runtime_iperf_concurrency.combined"
  cat "$CASES_DIR/runtime_iperf_concurrency.stdout" "$CASES_DIR/runtime_iperf_concurrency.stderr" >"$combined_out"
  if ! validate_iperf_output "$combined_out"; then
    RUNTIME_STATUS="FAIL"; record_failure "runtime_iperf_concurrency_acceptance" "IPERF_RUNTIME_EVIDENCE_INCOMPLETE" "validate iperf evidence"; return 1
  fi
  post_case_health "iperf_concurrency" "$baseline_iperf" || { RUNTIME_STATUS="FAIL"; record_failure "post_iperf_health" "RUNTIME_HEALTH_REGRESSION_OR_ORPHAN_IPERF" "health checks"; return 1; }

  log "RUNTIME_VALIDATION=PASS"
  return 0
}

latest_pass_report_for_phase() {
  local phase="$1"
  "$SUMMARY_PYTHON" - "$REPO_ROOT/runtime_reports" "$phase" "$REPORT_DIR" <<'PY'
import glob, json, os, sys
root, phase, current = sys.argv[1:]
paths = sorted(glob.glob(os.path.join(root, "ubuntu_phase44_45_validation_*", "summary.json")), reverse=True)
for path in paths:
    if os.path.dirname(path) == current:
        continue
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception:
        continue
    section = data.get(phase, {})
    status = section.get("status") if isinstance(section, dict) else section
    if status == "PASS" or (data.get("mode") == "all" and data.get("overall_status") == "PASS"):
        print(path)
        raise SystemExit(0)
raise SystemExit(1)
PY
}

validate_combined_summary() {
  local summary="$1"
  "$SUMMARY_PYTHON" - "$summary" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
text = json.dumps(data, ensure_ascii=False)
requirements = [
    ("firewall_counter_after_social_deny", "PASS"),
    ("phase44_firewall_runtime_check", "PASS"),
    ("concurrency_different_destinations", "PASS"),
    ("concurrency_same_destination_busy", "PASS"),
    ("NAT NOT REQUIRED AND RUNTIME PROVEN", None),
]
missing = []
for key, value in requirements:
    if key not in text or (value and value not in text[text.find(key):text.find(key)+500]):
        missing.append(key)
if "21/21" not in text and not ("dashboard_runtime_smoke" in text and "PASS" in text[text.find("dashboard_runtime_smoke"):text.find("dashboard_runtime_smoke")+500]):
    missing.append("dashboard_runtime_smoke_21_21")
if data.get("overall_status") != "PASS":
    missing.append("overall_status_PASS")
if missing:
    print("MISSING=" + ",".join(missing))
    raise SystemExit(1)
print("COMBINED_SUMMARY_VALID=YES")
PY
}

mode_combined() {
  COMBINED_STATUS="PASS"
  log "MODE=combined REPO_ROOT=$REPO_ROOT"
  if [[ ! -d "$REPO_ROOT/.git" ]]; then
    COMBINED_STATUS="BLOCKED"; record_blocked "combined_repository" "REPOSITORY_NOT_AVAILABLE" "$REPO_ROOT"; return 1
  fi
  refresh_git_state || true
  if [[ "$WORKING_TREE_CLEAN" != "true" ]]; then
    COMBINED_STATUS="BLOCKED"
    record_blocked "combined_dirty_worktree" "DIRTY_WORKTREE" "git status --porcelain"
    log "COMBINED_STATUS=BLOCKED REASON=DIRTY_WORKTREE"
    log "ACTION_REQUIRED=Create an explicit local checkpoint commit after user approval"
    return 1
  fi

  local static_evidence runtime_evidence
  if [[ "$MODE" == "all" && "$STATIC_STATUS" == "PASS" ]]; then
    static_evidence="$REPORT_DIR/summary.json"
  else
    static_evidence="$(latest_pass_report_for_phase static 2>/dev/null || true)"
  fi
  if [[ "$MODE" == "all" && "$RUNTIME_STATUS" == "PASS" ]]; then
    runtime_evidence="$REPORT_DIR/summary.json"
  else
    runtime_evidence="$(latest_pass_report_for_phase runtime 2>/dev/null || true)"
  fi
  if [[ -z "$static_evidence" || -z "$runtime_evidence" ]]; then
    COMBINED_STATUS="BLOCKED"
    record_blocked "combined_prior_gates" "MISSING_PRIOR_STATIC_OR_RUNTIME_PASS" "run static and runtime first"
    return 1
  fi
  printf 'static_evidence=%s\nruntime_evidence=%s\n' "$static_evidence" "$runtime_evidence" >"$ENV_DIR/combined_gate_evidence.txt"

  local script="$REPO_ROOT/scripts/phase44_45_combined_acceptance.sh"
  if [[ ! -f "$script" ]]; then
    COMBINED_STATUS="FAIL"; record_failure "combined_script" "COMBINED_ACCEPTANCE_SCRIPT_MISSING" "$script"; return 1
  fi
  if ! run_case "combined_acceptance" sudo -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 bash "$script"; then
    COMBINED_STATUS="FAIL"; record_failure "combined_acceptance" "COMBINED_ACCEPTANCE_EXIT_NONZERO" "sudo ... phase44_45_combined_acceptance.sh"; return 1
  fi
  local summary="$REPO_ROOT/runtime_reports/phase44_45_combined_summary.json"
  if [[ ! -f "$summary" ]]; then
    COMBINED_STATUS="FAIL"; record_failure "combined_summary" "COMBINED_SUMMARY_MISSING" "$summary"; return 1
  fi
  cp "$summary" "$REPORT_DIR/phase44_45_combined_summary.json"
  if ! run_case "combined_summary_validation" validate_combined_summary "$summary"; then
    COMBINED_STATUS="FAIL"; record_failure "combined_summary_validation" "COMBINED_SUMMARY_CONTRACT_FAILED" "validate $summary"; return 1
  fi
  log "COMBINED_STATUS=PASS"
  return 0
}

classify_failure() {
  local evidence safe_name stdout_file stderr_file
  if [[ -z "$FIRST_FAILURE" ]]; then
    FAILURE_CLASS=""
    return
  fi
  safe_name="$(sanitize_name "$FIRST_FAILURE")"
  stdout_file="$CASES_DIR/${safe_name}.stdout"
  stderr_file="$CASES_DIR/${safe_name}.stderr"
  evidence="${FIRST_FAILURE} ${FIRST_FAILURE_REASON} ${FIRST_FAILURE_COMMAND}"
  [[ -f "$stdout_file" ]] && evidence+=" $(tail -n 120 "$stdout_file" 2>/dev/null || true)"
  [[ -f "$stderr_file" ]] && evidence+=" $(tail -n 120 "$stderr_file" 2>/dev/null || true)"

  local has_code=0 has_env=0 has_runtime=0 has_test=0
  grep -Eqi 'ModuleNotFoundError|No module named|command not found|MISSING_COMMAND|MISSING_DEPENDENCY|NO_USABLE_PYTHON|PERMISSION|Permission denied|sudo:|NOT_A_GIT_REPOSITORY|REPOSITORY_NOT_FOUND|SOCKET_MISSING|OVS_BRIDGE_COUNT|Address already in use|port.*in use' <<<"$evidence" && has_env=1
  grep -Eqi 'DIRTY_WORKTREE|TOPOLOGY_NOT_RUNNING|CONTROLLER_NOT_RUNNING|BACKEND_NOT_RUNNING|FRONTEND_NOT_RUNNING|ORPHAN|STALE|RUNTIME_HEALTH|service.*not running|connection refused' <<<"$evidence" && has_runtime=1
  grep -Eqi 'SUMMARY|ACCEPTANCE|EVIDENCE_INCOMPLETE|LOCALE|PID|EXPECTED_RULE|TEST_OR_ACCEPTANCE|duration.*comma|assertion.*field|summary.*FAIL' <<<"$evidence" && has_test=1
  grep -Eqi 'Traceback|AssertionError|FAILED|PYTEST|SYNTAX|FIREWALL_COUNTER_CASE|IPERF_CONCURRENCY_CASE|GIT_CHECKPOINT_CODE|CODE_FAILURE|MISSING_DEEP_DEBUG_CLI|SOURCE_PATCH|race condition|global lock|response.*cross' <<<"$evidence" && has_code=1

  if (( (has_code || has_test) && (has_env || has_runtime) )); then
    FAILURE_CLASS="MIXED_ERROR"
  elif (( has_runtime )); then
    FAILURE_CLASS="RUNTIME_STATE_ERROR"
  elif (( has_env )); then
    FAILURE_CLASS="UBUNTU_ENVIRONMENT_ERROR"
  elif (( has_test )); then
    FAILURE_CLASS="TEST_OR_ACCEPTANCE_ERROR"
  elif (( has_code )); then
    FAILURE_CLASS="CODE_ERROR"
  else
    FAILURE_CLASS="UNKNOWN"
  fi
}

create_codex_prompt() {
  local target="$REPORT_DIR/codex_fix_prompt_$(sanitize_name "$FIRST_FAILURE").md"
  cat >"$target" <<EOF
# Codex fix prompt — $FIRST_FAILURE

Repository: $REPO_ROOT
Branch: $BRANCH
HEAD: $HEAD
Working tree clean: $WORKING_TREE_CLEAN

## Failure

- Case: $FIRST_FAILURE
- Failure class: $FAILURE_CLASS
- Reason: $FIRST_FAILURE_REASON
- Reproduction command: \`$FIRST_FAILURE_COMMAND\`

## Evidence

- Validation report: $REPORT_DIR
- Case stdout/stderr: inspect \`cases/$(sanitize_name "$FIRST_FAILURE").stdout\` and \`cases/$(sanitize_name "$FIRST_FAILURE").stderr\`.
- Product behavior evidence must not be changed merely to satisfy a bad assertion.

## Required workflow

1. Read the current source before editing.
2. Reproduce with the targeted command/test.
3. Identify the root cause from source and runtime evidence.
4. Apply the smallest relevant change.
5. Add or update a regression test.
6. Run targeted tests.
7. Run full pytest.
8. Run \`git diff --check\`.
9. Do not claim Ubuntu runtime PASS when running on Windows.
10. Report every file created or modified.

## Suspected areas

Start from the failing case and inspect only relevant product or test/acceptance infrastructure. For TEST_OR_ACCEPTANCE_ERROR, set:

\`TARGET_AREA=TEST_OR_ACCEPTANCE_INFRASTRUCTURE\`
\`PRODUCT_BEHAVIOR_EVIDENCE=PASS\`

## Forbidden actions

- Do not remove assertions or make tests always pass.
- Do not increase timeout as the primary fix.
- Do not remove security policy.
- Do not run git reset/clean/checkout/switch/stash/restore.
- Do not commit or push.

## Required final report

FILES CREATED:
FILES MODIFIED:
ROOT CAUSE:
FIX:
TARGETED TEST RESULT:
FULL PYTEST RESULT:
GIT DIFF CHECK:
REMAINING RISK:
FINAL STATUS:
EOF
  printf '%s' "$target"
}

create_ubuntu_script() {
  local kind="$1" target="$2"
  cat >"$target" <<EOF
#!/usr/bin/env bash
set -u -o pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1
CASE_NAME=$(printf '%q' "$FIRST_FAILURE")
REPO_ROOT=$(printf '%q' "$REPO_ROOT")
STAMP="\$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="\${REPO_ROOT}/runtime_reports/\${kind}_\${CASE_NAME}_\${STAMP}.log"
mkdir -p "\$(dirname "\$LOG_FILE")"
exec > >(tee -a "\$LOG_FILE") 2>&1
start="\$(date +%s)"
echo "CASE_NAME=\$CASE_NAME"
echo "FAILURE_CLASS=$(printf '%q' "$FAILURE_CLASS")"
echo "ORIGINAL_REASON=$(printf '%q' "$FIRST_FAILURE_REASON")"
echo "Repository diagnostics only; product source will not be modified."
cd "\$REPO_ROOT" || { echo "FINAL_STATUS=BLOCKED"; exit 2; }
git status --porcelain || true
git diff --check || true
pgrep -af '[t]opology_hybrid_sdn.py|[o]sken-manager|[c]ontroller_policy.py|[u]vicorn|[v]ite|[i]perf3' || true
ss -ltnp 2>/dev/null | grep -E ':(6653|8000|5173)([[:space:]]|$)' || true
command -v ovs-vsctl >/dev/null 2>&1 && ovs-vsctl list-br || true
command -v ip >/dev/null 2>&1 && ip netns list || true
for sock in /tmp/cch_mininet_control.sock /tmp/cch_osken_admin.sock; do stat "\$sock" 2>&1 || true; done
end="\$(date +%s)"
echo "UBUNTU_FIX_SUMMARY"
echo "CASE_NAME=\$CASE_NAME"
echo "FAILURE_CLASS=$(printf '%q' "$FAILURE_CLASS")"
echo "ROOT_CAUSE=Requires confirmation from collected diagnostics"
echo "CHANGES_APPLIED=None; diagnostic script only"
echo "VALIDATION_COMMAND=bash scripts/ubuntu_phase44_45_validation_gate.sh $MODE --reuse-running"
echo "VALIDATION_EXIT_CODE=NOT_RUN"
echo "DURATION_SECONDS=\$((end-start))"
echo "FINAL_STATUS=BLOCKED"
echo "LOG_FILE=\$LOG_FILE"
EOF
  chmod +x "$target"
  bash -n "$target"
}

create_runtime_recovery_script() {
  local target="$REPORT_DIR/runtime_state_recovery_$(sanitize_name "$FIRST_FAILURE").sh"
  cat >"$target" <<EOF
#!/usr/bin/env bash
set -u -o pipefail
export LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1
REPO_ROOT=$(printf '%q' "$REPO_ROOT")
cd "\$REPO_ROOT" || exit 2
echo "RUNTIME_STATE_DIAGNOSIS"
echo "CASE=$FIRST_FAILURE"
echo "REASON=$FIRST_FAILURE_REASON"
git status --porcelain || true
pgrep -af '[t]opology_hybrid_sdn.py|[o]sken-manager|[c]ontroller_policy.py|[u]vicorn|[v]ite|[i]perf3' || true
ss -ltnp 2>/dev/null | grep -E ':(6653|8000|5173)([[:space:]]|$)' || true
if [[ "$FIRST_FAILURE_REASON" == *DIRTY_WORKTREE* ]]; then
  echo "FINAL_STATUS=BLOCKED"
  echo "ACTION_REQUIRED=User approval is required before creating a local checkpoint commit"
else
  echo "FINAL_STATUS=BLOCKED"
  echo "ACTION_REQUIRED=Restore only the specifically missing runtime component, then rerun validation"
fi
EOF
  chmod +x "$target"
  bash -n "$target"
  printf '%s' "$target"
}

create_unknown_diagnostic() {
  local target="$REPORT_DIR/ubuntu_collect_more_evidence_$(sanitize_name "$FIRST_FAILURE").sh"
  create_ubuntu_script "ubuntu_collect_more_evidence" "$target"
  cat >>"$target" <<'EOF'
echo "EVIDENCE_COLLECTION_COMPLETE=YES"
echo "UNRESOLVED_QUESTION=Exact source, environment, or runtime cause is not proven"
echo "NEXT_REQUIRED_ARTIFACT=Complete script output and the last 200 log lines"
EOF
  bash -n "$target"
  printf '%s' "$target"
}

create_next_action() {
  local codex_prompt="" ubuntu_script="" next_command="" expected="" send_back=""
  classify_failure
  case "$FAILURE_CLASS" in
    CODE_ERROR|TEST_OR_ACCEPTANCE_ERROR)
      codex_prompt="$(create_codex_prompt)"
      next_command="Send CODEX FIX PROMPT to Codex"
      expected="A minimal patch, regression tests, full pytest and git diff --check results"
      send_back="Codex final report and patch/diff"
      log "FAILURE_CLASS=$FAILURE_CLASS"
      log "CODEX_PROMPT_CREATED=$codex_prompt"
      log "ACTION_REQUIRED=Send this prompt to Codex, then apply the returned patch on Ubuntu and rerun validation"
      ;;
    UBUNTU_ENVIRONMENT_ERROR)
      ubuntu_script="$REPORT_DIR/ubuntu_diagnose_$(sanitize_name "$FIRST_FAILURE").sh"
      create_ubuntu_script "ubuntu_diagnose" "$ubuntu_script"
      next_command="bash $ubuntu_script"
      expected="UBUNTU_FIX_SUMMARY"
      send_back="UBUNTU_FIX_SUMMARY and the last 200 lines of LOG_FILE"
      log "FAILURE_CLASS=UBUNTU_ENVIRONMENT_ERROR"
      log "UBUNTU_SCRIPT_CREATED=$ubuntu_script"
      ;;
    RUNTIME_STATE_ERROR)
      ubuntu_script="$(create_runtime_recovery_script)"
      next_command="bash $ubuntu_script"
      expected="Runtime state diagnosis without stopping a healthy topology"
      send_back="Script output and relevant process/port evidence"
      ;;
    MIXED_ERROR)
      codex_prompt="$(create_codex_prompt)"
      ubuntu_script="$REPORT_DIR/ubuntu_diagnose_or_fix_$(sanitize_name "$FIRST_FAILURE").sh"
      create_ubuntu_script "ubuntu_diagnose_or_fix" "$ubuntu_script"
      next_command="STEP_1=bash $ubuntu_script; STEP_2=send $codex_prompt to Codex"
      expected="Environment diagnosis first, then source patch"
      send_back="Ubuntu summary, log tail, Codex report and patch"
      ;;
    *)
      ubuntu_script="$(create_unknown_diagnostic)"
      next_command="bash $ubuntu_script"
      expected="EVIDENCE_COLLECTION_COMPLETE=YES"
      send_back="Evidence completion block and the last 200 log lines"
      ;;
  esac

  cat >"$REPORT_DIR/NEXT_ACTION.md" <<EOF
# NEXT ACTION

FIRST_FAILURE: $FIRST_FAILURE
FAILURE_CLASS: $FAILURE_CLASS
WHY_CLASSIFIED: $FIRST_FAILURE_REASON
CODEX_PROMPT: ${codex_prompt:-None}
UBUNTU_SCRIPT: ${ubuntu_script:-None}
COMMAND_TO_RUN: $next_command
EXPECTED_OUTPUT: $expected
WHAT_TO_SEND_BACK: $send_back
DO_NOT_DO: Do not reset, clean, checkout, switch, stash, restore, commit, push, remove assertions, weaken security policy, or increase timeout to hide serialization.
EOF

  CODEX_PROMPT_PATH="$codex_prompt"
  UBUNTU_SCRIPT_PATH="$ubuntu_script"
  NEXT_ACTION_PATH="$REPORT_DIR/NEXT_ACTION.md"
  RERUN_COMMAND="bash scripts/ubuntu_phase44_45_validation_gate.sh $MODE --reuse-running"
}

write_summary() {
  refresh_git_state || true
  runtime_health_snapshot
  local ended_at
  ended_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  MODE_VALUE="$MODE" OVERALL_VALUE="$OVERALL_STATUS" BRANCH_VALUE="$BRANCH" HEAD_VALUE="$HEAD" CLEAN_VALUE="$WORKING_TREE_CLEAN" \
  SOURCE_VALUE="$SOURCE_PATCH_PRECHECK_STATUS" PREFLIGHT_VALUE="$PREFLIGHT_STATUS" STATIC_VALUE="$STATIC_STATUS" RUNTIME_VALUE="$RUNTIME_STATUS" COMBINED_VALUE="$COMBINED_STATUS" \
  FIRST_VALUE="$FIRST_FAILURE" FIRST_REASON_VALUE="$FIRST_FAILURE_REASON" FIRST_COMMAND_VALUE="$FIRST_FAILURE_COMMAND" FAILURE_CLASS_VALUE="${FAILURE_CLASS:-}" \
  CODEX_PROMPT_VALUE="${CODEX_PROMPT_PATH:-}" UBUNTU_SCRIPT_VALUE="${UBUNTU_SCRIPT_PATH:-}" NEXT_ACTION_VALUE="${NEXT_ACTION_PATH:-}" RERUN_VALUE="${RERUN_COMMAND:-}" \
  REPORT_VALUE="$REPORT_DIR" STARTED_VALUE="$STARTED_AT" ENDED_VALUE="$ended_at" TOPOLOGY_VALUE="$TOPOLOGY_RUNNING" CONTROLLER_VALUE="$CONTROLLER_RUNNING" BACKEND_VALUE="$BACKEND_RUNNING" FRONTEND_VALUE="$FRONTEND_RUNNING" OVS_VALUE="$OVS_BRIDGE_COUNT" \
    "$SUMMARY_PYTHON" - "$CASE_JSONL" "$SUMMARY_JSON" <<'PY'
import json, os, sys
cases_path, summary_path = sys.argv[1:]
cases = []
try:
    with open(cases_path, encoding="utf-8") as handle:
        cases = [json.loads(line) for line in handle if line.strip()]
except FileNotFoundError:
    pass
failed = []
for item in cases:
    if item.get("status") in {"FAIL", "BLOCKED"}:
        is_first = item.get("case") == os.environ.get("FIRST_VALUE")
        failed.append({
            "case": item.get("case"),
            "status": item.get("status"),
            "failure_class": os.environ.get("FAILURE_CLASS_VALUE", "") if is_first else "",
            "reason": os.environ.get("FIRST_REASON_VALUE", "") if is_first else item.get("reason", ""),
            "evidence": [item.get("stdout"), item.get("stderr")],
            "generated_artifacts": [p for p in [os.environ.get("CODEX_PROMPT_VALUE"), os.environ.get("UBUNTU_SCRIPT_VALUE"), os.environ.get("NEXT_ACTION_VALUE")] if p],
        })
clean_raw = os.environ.get("CLEAN_VALUE", "unknown")
clean = True if clean_raw == "true" else False if clean_raw == "false" else None
first_failure = None
if os.environ.get("FIRST_VALUE"):
    first_failure = {
        "case": os.environ.get("FIRST_VALUE"),
        "reason": os.environ.get("FIRST_REASON_VALUE"),
        "command": os.environ.get("FIRST_COMMAND_VALUE"),
    }
obj = {
    "overall_status": os.environ["OVERALL_VALUE"],
    "mode": os.environ["MODE_VALUE"],
    "started_at": os.environ["STARTED_VALUE"],
    "ended_at": os.environ["ENDED_VALUE"],
    "branch": os.environ.get("BRANCH_VALUE", ""),
    "head": os.environ.get("HEAD_VALUE", ""),
    "working_tree_clean": clean,
    "source_patch_precheck": {"status": os.environ["SOURCE_VALUE"]},
    "preflight": {"status": os.environ["PREFLIGHT_VALUE"]},
    "static": {"status": os.environ["STATIC_VALUE"]},
    "runtime": {"status": os.environ["RUNTIME_VALUE"]},
    "combined": {"status": os.environ["COMBINED_VALUE"]},
    "runtime_health": {
        "topology_running": os.environ.get("TOPOLOGY_VALUE") == "true",
        "controller_running": os.environ.get("CONTROLLER_VALUE") == "true",
        "backend_running": os.environ.get("BACKEND_VALUE") == "true",
        "frontend_running": os.environ.get("FRONTEND_VALUE") == "true",
        "ovs_bridge_count": int(os.environ.get("OVS_VALUE", "0") or 0),
    },
    "first_failure": first_failure,
    "cases": cases,
    "failed_cases": failed,
    "artifacts": [os.environ["REPORT_VALUE"]],
    "failure_triage": {
        "first_failure": os.environ.get("FIRST_VALUE", ""),
        "failure_class": os.environ.get("FAILURE_CLASS_VALUE", ""),
        "classification_evidence": [x for x in [os.environ.get("FIRST_REASON_VALUE"), os.environ.get("FIRST_COMMAND_VALUE")] if x],
        "codex_prompt": os.environ.get("CODEX_PROMPT_VALUE") or None,
        "ubuntu_script": os.environ.get("UBUNTU_SCRIPT_VALUE") or None,
        "next_action_file": os.environ.get("NEXT_ACTION_VALUE") or None,
        "rerun_command": os.environ.get("RERUN_VALUE") or None,
    },
}
with open(summary_path, "w", encoding="utf-8") as handle:
    json.dump(obj, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PY
}

finalize() {
  if [[ "$OVERALL_STATUS" != "PASS" ]]; then
    create_next_action
  fi
  write_summary
  log "SUMMARY_JSON=$SUMMARY_JSON"
  log "FINAL_STATUS=$OVERALL_STATUS"
  log "FIRST_FAILURE=${FIRST_FAILURE:-NONE}"
  log "FAILURE_CLASS=${FAILURE_CLASS:-NONE}"
  log "TOPOLOGY_STILL_RUNNING=$TOPOLOGY_RUNNING"
  log "CONTROLLER_STILL_RUNNING=$CONTROLLER_RUNNING"
  log "BACKEND_STILL_RUNNING=$BACKEND_RUNNING"
  log "FRONTEND_STILL_RUNNING=$FRONTEND_RUNNING"
  log "OVS_BRIDGE_COUNT=$OVS_BRIDGE_COUNT"
}

parse_args() {
  if (( $# == 0 )); then
    usage
    exit 2
  fi
  case "$1" in
    -h|--help) usage; exit 0 ;;
    preflight|static|runtime|combined|all) MODE="$1"; shift ;;
    *) printf 'Unknown mode: %s\n' "$1" >&2; usage; exit 2 ;;
  esac
  while (( $# > 0 )); do
    case "$1" in
      --start-dashboard) START_DASHBOARD=1 ;;
      --reuse-running) REUSE_RUNNING=1 ;;
      --report-dir)
        shift
        (( $# > 0 )) || { echo "--report-dir requires a path" >&2; exit 2; }
        REPORT_DIR="$1"
        ;;
      --verbose) VERBOSE=1 ;;
      -h|--help) usage; exit 0 ;;
      *) printf 'Unknown option: %s\n' "$1" >&2; usage; exit 2 ;;
    esac
    shift
  done
}

parse_args "$@"

if [[ -z "$REPORT_DIR" ]]; then
  REPORT_DIR="$REPO_ROOT/runtime_reports/ubuntu_phase44_45_validation_${STAMP}"
fi
CASES_DIR="$REPORT_DIR/cases"
ENV_DIR="$REPORT_DIR/environment"
LOG_FILE="$REPORT_DIR/validation.log"
SUMMARY_JSON="$REPORT_DIR/summary.json"
CASE_JSONL="$REPORT_DIR/cases.jsonl"
mkdir -p "$CASES_DIR" "$ENV_DIR"
: >"$LOG_FILE"
: >"$CASE_JSONL"

SUMMARY_PYTHON="$(command -v python3 2>/dev/null || true)"
if [[ -z "$SUMMARY_PYTHON" ]]; then
  echo "python3 is required to write validation artifacts." >&2
  exit 2
fi

CODEX_PROMPT_PATH=""
UBUNTU_SCRIPT_PATH=""
NEXT_ACTION_PATH=""
RERUN_COMMAND=""

log "VALIDATION_START mode=$MODE report_dir=$REPORT_DIR reuse_running=$REUSE_RUNNING start_dashboard=$START_DASHBOARD"

rc=0
case "$MODE" in
  preflight)
    mode_preflight || rc=$?
    ;;
  static)
    mode_static || rc=$?
    ;;
  runtime)
    mode_runtime || rc=$?
    ;;
  combined)
    mode_combined || rc=$?
    ;;
  all)
    mode_preflight || rc=$?
    if (( rc == 0 )); then mode_static || rc=$?; fi
    if (( rc == 0 )); then mode_runtime || rc=$?; fi
    if (( rc == 0 )); then mode_combined || rc=$?; fi
    ;;
esac

finalize

if [[ "$OVERALL_STATUS" == "PASS" ]]; then
  exit 0
fi
if [[ "$OVERALL_STATUS" == "BLOCKED" ]]; then
  exit 3
fi
exit "${rc:-1}"
