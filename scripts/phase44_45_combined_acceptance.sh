#!/usr/bin/env bash
set -uo pipefail

# Combined Acceptance chi chay tren Ubuntu khi topology, controller va dashboard da san sang.
# Script khong sua source-of-truth, khong tat firewall va khong thay expected result.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_ROOT="$ROOT_DIR/runtime_reports"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_DIR="$REPORT_ROOT/phase44_45_combined_$STAMP"
LOG_FILE="$REPORT_ROOT/phase44_45_combined_$STAMP.log"
SUMMARY_FILE="$REPORT_ROOT/phase44_45_combined_summary.json"
RESULTS_FILE="$REPORT_DIR/results.tsv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TOKEN_FILE="$ROOT_DIR/logs/operator.token"
OPERATOR_TOKEN=""
AUTH_ARGS=()
FAILURES=0

mkdir -p "$REPORT_DIR"
: > "$LOG_FILE"
: > "$RESULTS_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

record_result() {
  local name="$1" status="$2" duration="$3" exit_code="$4"
  printf '%s\t%s\t%s\t%s\n' "$name" "$status" "$duration" "$exit_code" >> "$RESULTS_FILE"
}

run_case() {
  local name="$1"
  shift
  local stdout_file="$REPORT_DIR/${name}.stdout"
  local stderr_file="$REPORT_DIR/${name}.stderr"
  local started ended duration exit_code status
  started="$(date +%s%N)"
  echo
  echo "================================================================"
  echo "CASE $name"
  echo "================================================================"
  "$@" > "$stdout_file" 2> "$stderr_file"
  exit_code=$?
  ended="$(date +%s%N)"
  duration="$(awk -v start="$started" -v end="$ended" 'BEGIN { printf "%.3f", (end-start)/1000000000 }')"
  echo "--- STDOUT ($stdout_file) ---"
  cat "$stdout_file"
  echo "--- STDERR ($stderr_file) ---"
  cat "$stderr_file"
  echo "EXIT_CODE=$exit_code DURATION=${duration}s"
  if [[ "$exit_code" -eq 0 ]]; then
    status="PASS"
    echo "PASS $name"
  else
    status="FAIL"
    FAILURES=$((FAILURES + 1))
    echo "FAIL $name"
  fi
  record_result "$name" "$status" "$duration" "$exit_code"
  return 0
}

api_get() {
  local path="$1" output="$2"
  curl -fsS --max-time 20 "http://127.0.0.1:8000${path}" > "$output"
  cat "$output"
}

api_post() {
  local path="$1" body="$2" output="$3"
  curl -fsS --max-time 70 -X POST \
    -H 'Content-Type: application/json' \
    "${AUTH_ARGS[@]}" \
    --data "$body" "http://127.0.0.1:8000${path}" > "$output"
  cat "$output"
}

validate_json_contract() {
  "$PYTHON_BIN" - "$REPORT_DIR/api_topology.json" "$REPORT_DIR/api_firewalls.json" "$REPORT_DIR/api_health.json" <<'PY'
import json
import sys

topology, firewalls, health = (json.load(open(path, encoding="utf-8")) for path in sys.argv[1:])
assert topology["site_ids"] == ["hq", "telesale"]
assert len(topology["logical_switches"]) == 9
assert topology["runtime_bridge_map"]["access_backoffice"] == "access_bo"
assert {item["name"] for item in firewalls["firewalls"]} == {"fw_hq", "fw_telesale"}
assert firewalls["phase44_runtime"]["status"] in {"pending", "verified"}
required = ("backend", "controller", "mininet_topology", "mininet_control_agent", "openvswitch")
assert all(health["components"][name]["status"] == "online" for name in required)
print("two-site API contract and required health components are online")
PY
}

validate_ping_response() {
  local response_file="$1" expected="$2"
  "$PYTHON_BIN" - "$response_file" "$expected" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
expected = sys.argv[2]
decision = payload.get("decision") or {}
assert decision.get("action") == expected
assert isinstance(decision.get("path"), list) and decision["path"]
if expected == "allow":
    assert payload.get("ok") is True
else:
    assert payload.get("ok") is False
    assert payload.get("error_code") == "POLICY_DENIED"
print({"action": decision.get("action"), "blocked_at": decision.get("blocked_at"), "path": decision.get("path")})
PY
}

validate_link_recovery() {
  "$PYTHON_BIN" - "$REPORT_DIR/link_fail.json" "$REPORT_DIR/link_recover.json" <<'PY'
import json
import sys

failed = json.load(open(sys.argv[1], encoding="utf-8"))
recovered = json.load(open(sys.argv[2], encoding="utf-8"))
assert failed.get("ok") is True and failed.get("status") == "down"
assert recovered.get("ok") is True and recovered.get("status") == "up"
print({"failed_link": failed.get("link_id"), "recovered_link": recovered.get("link_id")})
PY
}

flow_case() {
  local switch="$1"
  ovs-vsctl br-exists "$switch" || return 1
  ovs-ofctl -O OpenFlow13 dump-flows "$switch" | tee "$REPORT_DIR/flows_${switch}.txt"
  grep -q 'actions=' "$REPORT_DIR/flows_${switch}.txt"
}

firewall_case() {
  local firewall="$1"
  ip netns exec "$firewall" nft -a list table inet cch_filter
  ip netns exec "$firewall" sysctl -n net.ipv4.ip_forward | grep -qx '1'
}

read_operator_token() {
  [[ -s "$TOKEN_FILE" ]] || return 1
  OPERATOR_TOKEN="$(< "$TOKEN_FILE")"
  [[ -n "$OPERATOR_TOKEN" ]] || return 1
  AUTH_ARGS=(-H "X-CCH-Operator-Token: $OPERATOR_TOKEN")
  echo "Operator token da nap tu $TOKEN_FILE; gia tri token khong duoc in ra."
}

api_contract_case() {
  api_get /api/topology "$REPORT_DIR/api_topology.json" || return 1
  api_get /api/firewalls "$REPORT_DIR/api_firewalls.json" || return 1
  api_get /api/health "$REPORT_DIR/api_health.json" || return 1
  validate_json_contract
}

ping_case() {
  local source="$1" destination="$2" expected="$3" output="$4"
  local body
  body="{\"source\":\"$source\",\"destination\":\"$destination\"}"
  api_post /api/test/ping "$body" "$output" || return 1
  validate_ping_response "$output" "$expected"
}

social_counter_case() {
  local before="$REPORT_DIR/firewalls_before_social.json"
  local after="$REPORT_DIR/firewalls_after_social.json"
  api_get /api/firewalls "$before" || return 1
  ping_case h20_01 hsocial deny "$REPORT_DIR/ping_social_deny.json" || return 1
  api_get /api/firewalls "$after" || return 1
  "$PYTHON_BIN" - "$before" "$after" <<'PY'
import json
import sys

before = json.load(open(sys.argv[1], encoding="utf-8"))
after = json.load(open(sys.argv[2], encoding="utf-8"))
before_fw = next(item for item in before["firewalls"] if item["name"] == "fw_hq")
after_fw = next(item for item in after["firewalls"] if item["name"] == "fw_hq")
before_packets = ((before_fw.get("counters") or {}).get("social_deny") or {}).get("packets")
after_packets = ((after_fw.get("counters") or {}).get("social_deny") or {}).get("packets")
assert before_packets is not None and after_packets is not None and after_packets > before_packets
print({"packets_before": before_packets, "packets_after": after_packets})
PY
}

link_fail_recover_case() {
  local fail_file="$REPORT_DIR/link_fail.json"
  local recover_file="$REPORT_DIR/link_recover.json"
  api_post /api/link/fail '{"link_id":"access_hq_a-core_hq"}' "$fail_file" || return 1
  api_post /api/link/recover '{"link_id":"access_hq_a-core_hq"}' "$recover_file" || return 1
  validate_link_recovery
}

run_case linux_root_preflight bash -c '[[ "$(uname -s)" == "Linux" && "$(id -u)" -eq 0 ]]'
run_case dependency_python command -v "$PYTHON_BIN"
run_case dependency_curl command -v curl
run_case dependency_ss command -v ss
run_case dependency_ovs_vsctl command -v ovs-vsctl
run_case dependency_ovs_ofctl command -v ovs-ofctl
run_case operator_token_preflight read_operator_token
run_case controller_port bash -c 'ss -ltn | grep -Eq ":6653[[:space:]]"'
run_case backend_port bash -c 'ss -ltn | grep -Eq ":8000[[:space:]]"'
run_case frontend_port bash -c 'ss -ltn | grep -Eq ":5173[[:space:]]"'
run_case mininet_topology_process pgrep -f '[t]opology_hybrid_sdn.py'
run_case named_firewall_namespaces bash -c 'names="$(ip netns list)"; grep -q "^fw_hq" <<< "$names" && grep -q "^fw_telesale" <<< "$names"'
run_case ovs_inventory ovs-vsctl show
for switch in access_hq_a access_hq_b access_hq_c access_hq_it voice_access core_hq access_telesale dist_telesale; do
  run_case "ovs_${switch}" flow_case "$switch"
done
run_case ovs_access_backoffice flow_case access_bo
run_case firewall_fw_hq firewall_case fw_hq
run_case firewall_fw_telesale firewall_case fw_telesale

run_case api_contract api_contract_case
run_case ping_h30_to_voice ping_case h30_01 h90 allow "$REPORT_DIR/ping_allow.json"
run_case ping_project_isolation ping_case h20_01 h30_01 deny "$REPORT_DIR/ping_deny.json"
run_case firewall_counter_after_social_deny social_counter_case

run_case policy_reload "$PYTHON_BIN" "$ROOT_DIR/sdn_mpls_demo/firewall_nftables.py" --apply
run_case link_fail_recover link_fail_recover_case

# Hai runner nay bao phu iperf TCP/UDP, Voice Quality, concurrency, log safety va ping sau iperf.
run_case phase44_firewall_runtime_check "$PYTHON_BIN" "$ROOT_DIR/scripts/phase44_firewall_runtime_check.py"
run_case dashboard_runtime_smoke "$PYTHON_BIN" "$ROOT_DIR/scripts/dashboard_runtime_smoke_test.py"

"$PYTHON_BIN" - "$RESULTS_FILE" "$SUMMARY_FILE" "$LOG_FILE" "$REPORT_DIR" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

results_file, summary_file, log_file, report_dir = map(Path, sys.argv[1:])
results = []
for line in results_file.read_text(encoding="utf-8").splitlines():
    name, status, duration, exit_code = line.split("\t")
    results.append({
        "name": name,
        "status": status,
        "duration_seconds": float(duration),
        "exit_code": int(exit_code),
        "raw_stdout": str(report_dir / f"{name}.stdout"),
        "raw_stderr": str(report_dir / f"{name}.stderr"),
    })
phase44_reports = sorted(report_dir.parent.glob("phase44_firewall_*.json"))
nat_conclusion = "NAT REQUIREMENT NOT YET CONCLUDED"
phase44_verified = False
if phase44_reports:
    payload = json.loads(phase44_reports[-1].read_text(encoding="utf-8"))
    nat_conclusion = str(payload.get("nat_conclusion") or nat_conclusion)
    phase44_verified = payload.get("passed") is True and nat_conclusion == "NAT NOT REQUIRED AND RUNTIME PROVEN"
summary = {
    "suite": "Phase 44/45 Combined Acceptance",
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "overall_status": "PASS" if results and all(item["status"] == "PASS" for item in results) else "FAIL",
    "phase44_runtime_verified": phase44_verified,
    "nat_conclusion": nat_conclusion,
    "runtime_status_rule": "Phase 44 remains pending unless firewall and NAT evidence are real and complete.",
    "results": results,
    "log_file": str(log_file),
    "report_directory": str(report_dir),
}
summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"SUMMARY={summary_file}")
print(json.dumps({"overall_status": summary["overall_status"], "phase44_runtime_verified": phase44_verified, "nat_conclusion": nat_conclusion}, ensure_ascii=False))
PY

echo
echo "Combined Acceptance artifacts:"
echo "  LOG=$LOG_FILE"
echo "  DIR=$REPORT_DIR"
echo "  SUMMARY=$SUMMARY_FILE"
if [[ "$FAILURES" -eq 0 ]]; then
  echo "PHASE 44/45 COMBINED ACCEPTANCE: PASS"
  exit 0
fi
echo "PHASE 44/45 COMBINED ACCEPTANCE: FAIL ($FAILURES case(s))"
exit 1
