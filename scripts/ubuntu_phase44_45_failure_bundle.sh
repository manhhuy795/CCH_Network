#!/usr/bin/env bash

set -u -o pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONUTF8=1

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${CCH_REPO_ROOT:-$(cd -- "$SCRIPT_DIR/.." && pwd)}"
REPORT_DIR=""
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/ubuntu_phase44_45_failure_bundle.sh [--report-dir <validation-report-dir>]

Creates:
  runtime_reports/ubuntu_phase44_45_failure_bundle_<UTC timestamp>.tar.gz

The bundle excludes operator tokens, credentials, private keys and other sensitive files.
It only collects evidence and does not modify product source or runtime state.
EOF
}

while (( $# > 0 )); do
  case "$1" in
    --report-dir)
      shift
      (( $# > 0 )) || { echo "--report-dir requires a path" >&2; exit 2; }
      REPORT_DIR="$1"
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

RUNTIME_ROOT="$REPO_ROOT/runtime_reports"
mkdir -p "$RUNTIME_ROOT"
if [[ -z "$REPORT_DIR" ]]; then
  REPORT_DIR="$(find "$RUNTIME_ROOT" -maxdepth 1 -type d -name 'ubuntu_phase44_45_validation_*' -printf '%T@ %p\n' 2>/dev/null | sort -nr | awk 'NR==1{$1=""; sub(/^ /,""); print; exit}')"
fi
if [[ -z "$REPORT_DIR" || ! -d "$REPORT_DIR" ]]; then
  echo "No validation report directory found." >&2
  exit 2
fi

STAGE="$(mktemp -d "$RUNTIME_ROOT/.ubuntu_phase44_45_bundle_stage_XXXXXX")"
BUNDLE="$RUNTIME_ROOT/ubuntu_phase44_45_failure_bundle_${STAMP}.tar.gz"
LOG="$STAGE/bundle_creation.log"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"; }
run_readonly() {
  local name="$1"; shift
  local start end rc
  start="$(date +%s%3N 2>/dev/null || date +%s000)"
  log "COMMAND_START name=$name command=$*"
  "$@" >"$STAGE/${name}.stdout" 2>"$STAGE/${name}.stderr"
  rc=$?
  end="$(date +%s%3N 2>/dev/null || date +%s000)"
  log "COMMAND_END name=$name exit_code=$rc duration_ms=$((end-start))"
  return 0
}

copy_safe_file() {
  local source="$1" destination="$2"
  [[ -f "$source" ]] || return 0
  case "$(basename "$source")" in
    operator.token|*.pem|*.key|id_rsa|id_ed25519|credentials*|*.p12|*.pfx) return 0 ;;
  esac
  mkdir -p "$(dirname "$destination")"
  cp "$source" "$destination"
}

log "BUNDLE_START report_dir=$REPORT_DIR"
mkdir -p "$STAGE/validation" "$STAGE/latest" "$STAGE/runtime"

for name in summary.json validation.log cases.jsonl NEXT_ACTION.md; do
  copy_safe_file "$REPORT_DIR/$name" "$STAGE/validation/$name"
done
if [[ -d "$REPORT_DIR/cases" ]]; then
  mkdir -p "$STAGE/validation/cases"
  find "$REPORT_DIR/cases" -maxdepth 1 -type f ! -name 'operator.token' ! -name '*.pem' ! -name '*.key' -exec cp {} "$STAGE/validation/cases/" \;
fi
find "$REPORT_DIR" -maxdepth 1 -type f \( -name 'codex_fix_prompt_*.md' -o -name 'ubuntu_diagnose_*.sh' -o -name 'ubuntu_fix_*.sh' -o -name 'runtime_state_recovery_*.sh' -o -name 'ubuntu_collect_more_evidence_*.sh' -o -name 'ubuntu_diagnose_or_fix_*.sh' \) -exec cp {} "$STAGE/validation/" \;

latest_copy() {
  local pattern="$1" label="$2" file
  file="$(find "$RUNTIME_ROOT" -maxdepth 2 -type f -name "$pattern" -printf '%T@ %p\n' 2>/dev/null | sort -nr | awk 'NR==1{$1=""; sub(/^ /,""); print; exit}')"
  [[ -n "$file" ]] && copy_safe_file "$file" "$STAGE/latest/${label}_$(basename "$file")"
}
latest_copy 'ubuntu_phase44_45_debug_*.json' deep_debug
latest_copy 'ubuntu_phase44_45_debug_*.log' deep_debug
latest_copy 'dashboard_runtime_*.json' dashboard_runtime
latest_copy 'dashboard_runtime_*.log' dashboard_runtime
latest_copy 'phase44_firewall_*.json' phase44_runtime
latest_copy 'phase44_firewall_*.log' phase44_runtime
latest_copy 'phase44_45_combined_summary.json' combined
latest_copy 'phase44_45_combined_*.log' combined

if [[ -d "$REPO_ROOT/.git" ]]; then
  run_readonly git_status git -C "$REPO_ROOT" status --porcelain
  run_readonly git_diff_stat git -C "$REPO_ROOT" diff --stat
  run_readonly git_diff_check git -C "$REPO_ROOT" diff --check
  run_readonly git_diff git -C "$REPO_ROOT" diff --no-ext-diff --
  run_readonly git_log git -C "$REPO_ROOT" log -10 --oneline --decorate
fi
run_readonly versions bash -lc 'python3 --version 2>&1; command -v mn >/dev/null && timeout 10 mn --version; command -v ovs-vsctl >/dev/null && timeout 10 ovs-vsctl --version; command -v osken-manager >/dev/null && timeout 10 osken-manager --version; command -v nft >/dev/null && timeout 10 nft --version; command -v iperf3 >/dev/null && timeout 10 iperf3 --version; command -v node >/dev/null && timeout 10 node --version; command -v npm >/dev/null && timeout 10 npm --version'
run_readonly processes bash -lc "pgrep -af '[t]opology_hybrid_sdn.py|[o]sken-manager|[c]ontroller_policy.py|[u]vicorn|[v]ite|[i]perf3' || true"
run_readonly ports bash -lc "ss -ltnp 2>/dev/null | grep -E ':(6653|8000|5173)([[:space:]]|$)' || true"
command -v ovs-vsctl >/dev/null 2>&1 && run_readonly ovs_inventory timeout 10 ovs-vsctl show
command -v ovs-vsctl >/dev/null 2>&1 && run_readonly ovs_controllers timeout 15 bash -lc 'for br in $(ovs-vsctl list-br 2>/dev/null); do echo "BRIDGE=$br"; ovs-vsctl get-controller "$br"; ovs-vsctl get Bridge "$br" fail_mode 2>/dev/null || true; done'
command -v ip >/dev/null 2>&1 && run_readonly namespaces timeout 10 ip netns list
run_readonly socket_metadata bash -lc 'for sock in /tmp/cch_mininet_control.sock /tmp/cch_osken_admin.sock; do echo "SOCKET=$sock"; stat "$sock" 2>&1 || true; done'
if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
  run_readonly nft_fw_hq timeout 15 sudo -n ip netns exec fw_hq nft list ruleset
  run_readonly nft_fw_telesale timeout 15 sudo -n ip netns exec fw_telesale nft list ruleset
else
  printf 'sudo non-interactive access unavailable; nft namespace evidence not collected.\n' >"$STAGE/nft_collection_blocked.txt"
fi

for candidate in \
  "$REPO_ROOT/logs/backend.log" "$REPO_ROOT/backend.log" \
  "$REPO_ROOT/logs/frontend.log" "$REPO_ROOT/frontend.log" \
  "$REPO_ROOT/logs/controller.log" "$REPO_ROOT/controller.log"; do
  if [[ -f "$candidate" ]]; then
    base="$(basename "$candidate")"
    tail -n 300 "$candidate" >"$STAGE/runtime/${base}.tail" 2>&1 || true
  fi
done

# Security scan: reject sensitive filenames and high-confidence secret contents.
if find "$STAGE" -type f \( -name 'operator.token' -o -name '*.pem' -o -name '*.key' -o -name 'id_rsa' -o -name 'id_ed25519' -o -name '*.p12' -o -name '*.pfx' \) | grep -q .; then
  echo "SECURITY_SCAN=FAIL reason=SENSITIVE_FILENAME" >&2
  exit 1
fi
if grep -RIEq --exclude='bundle_creation.log' -- '-----BEGIN ([A-Z ]+ )?PRIVATE KEY-----|Authorization:[[:space:]]*Bearer[[:space:]]+[A-Za-z0-9._~+/-]{16,}|operator[_-]?token[[:space:]]*[:=][[:space:]]*[^[:space:]]{8,}|password[[:space:]]*[:=][[:space:]]*[^[:space:]]{8,}' "$STAGE"; then
  echo "SECURITY_SCAN=FAIL reason=SECRET_PATTERN" >&2
  exit 1
fi
log "SECURITY_SCAN=PASS"

tar -C "$STAGE" -czf "$BUNDLE" .
log "BUNDLE_CREATED=$BUNDLE"
printf 'FAILURE_BUNDLE=%s\n' "$BUNDLE"
