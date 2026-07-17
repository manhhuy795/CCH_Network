#!/usr/bin/env bash
set -uo pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONUTF8=1

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/sdn_mpls_demo/runtime"
SOCKET_PATH="${CCH_MININET_CONTROL_SOCKET:-/tmp/cch_mininet_control.sock}"
CONTROL_TOKEN="${CCH_MININET_CONTROL_TOKEN:-cch-local-mininet-token}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="$RUNTIME_DIR/phase42_resource_gate_${TIMESTAMP}.log"
FAILURES=0

mkdir -p "$RUNTIME_DIR"
exec > >(tee "$REPORT") 2>&1

pass() {
  echo "PASS $*"
}

fail() {
  echo "FAIL $*"
  FAILURES=$((FAILURES + 1))
}

section() {
  echo
  echo "================================================================"
  echo "$*"
  echo "================================================================"
}

agent_request() {
  local command="$1"
  sudo env \
    CCH_GATE_SOCKET="$SOCKET_PATH" \
    CCH_GATE_TOKEN="$CONTROL_TOKEN" \
    CCH_GATE_COMMAND="$command" \
    python3 - <<'PY'
import json
import os
import socket

request = {
    "token": os.environ["CCH_GATE_TOKEN"],
    "command": os.environ["CCH_GATE_COMMAND"],
    "request_id": "phase42-resource-gate",
}
client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
client.settimeout(5)
client.connect(os.environ["CCH_GATE_SOCKET"])
client.sendall((json.dumps(request) + "\n").encode("utf-8"))
chunks = bytearray()
while b"\n" not in chunks:
    chunk = client.recv(65536)
    if not chunk:
        raise RuntimeError("Agent closed the socket before returning JSON")
    chunks.extend(chunk)
client.close()
payload = json.loads(bytes(chunks).split(b"\n", 1)[0].decode("utf-8"))
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
PY
}

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "PHASE BLOCKED: script nay chi duoc chay tren Ubuntu/Linux."
  exit 2
fi

if ! sudo -v; then
  echo "PHASE BLOCKED: khong xac thuc duoc sudo."
  exit 2
fi

section "PHASE 42 UBUNTU RESOURCE GATE"
date --iso-8601=seconds
echo "Report: $REPORT"

section "1. BASELINE TRUOC KHI BUILD"
if [[ -s "$RUNTIME_DIR/phase42_resource_baseline.log" ]]; then
  cat "$RUNTIME_DIR/phase42_resource_baseline.log"
else
  fail "Khong co phase42_resource_baseline.log tu run_topology.sh"
fi

section "2. TOPOLOGY PROCESS VA MININET CLI"
TOPOLOGY_PID="$(pgrep -fo '[t]opology_hybrid_sdn.py' || true)"
if [[ -n "$TOPOLOGY_PID" ]] && kill -0 "$TOPOLOGY_PID" 2>/dev/null; then
  ps -o pid,ppid,tty,stat,%cpu,%mem,rss,etime,cmd -p "$TOPOLOGY_PID"
  TOPOLOGY_TTY="$(ps -o tty= -p "$TOPOLOGY_PID" | xargs)"
  pass "Topology process dang song, PID=$TOPOLOGY_PID, TTY=$TOPOLOGY_TTY"
  if [[ -z "$TOPOLOGY_TTY" || "$TOPOLOGY_TTY" == "?" ]]; then
    fail "Topology process khong gan TTY; khong xac nhan duoc Mininet CLI interactive"
  else
    pass "Mininet CLI co TTY interactive"
  fi
else
  fail "Khong tim thay topology_hybrid_sdn.py dang chay"
fi

echo "--- raw mininet namespace process inventory ---"
pgrep -af 'mininet:' || true
NAMESPACE_REPORT="$(
  ps -eo args= | python3 "$ROOT_DIR/scripts/phase42_namespace_inventory.py"
)"
NAMESPACE_EXIT=$?
echo "$NAMESPACE_REPORT"
echo "EXIT_CODE_NAMESPACE_INVENTORY=$NAMESPACE_EXIT"
if [[ "$NAMESPACE_EXIT" -ne 0 ]]; then
  FAILURES=$((FAILURES + 1))
fi

section "3. MININET CONTROL AGENT"
echo "SOCKET_PATH=$SOCKET_PATH"
if [[ -S "$SOCKET_PATH" ]]; then
  ls -l "$SOCKET_PATH"
  AGENT_HEALTH="$(agent_request HEALTH 2>&1)"
  AGENT_EXIT=$?
  echo "$AGENT_HEALTH"
  echo "EXIT_CODE=$AGENT_EXIT"
  if [[ "$AGENT_EXIT" -eq 0 ]] && python3 -c 'import json,sys; p=json.loads(sys.stdin.read()); raise SystemExit(0 if p.get("ok") and p.get("agent_alive") else 1)' <<<"$AGENT_HEALTH"; then
    pass "Control Agent HEALTH"
  else
    fail "Control Agent HEALTH khong dat"
  fi

  LIVE_STATUS="$(agent_request LIVE_STATUS 2>&1)"
  LIVE_EXIT=$?
  echo "$LIVE_STATUS"
  echo "EXIT_CODE=$LIVE_EXIT"
  if [[ "$LIVE_EXIT" -eq 0 ]] && python3 -c 'import json,sys; p=json.loads(sys.stdin.read()); raise SystemExit(0 if p.get("user_hosts_online") == 110 and len(p.get("bridges", {})) == 9 and all(p.get("bridges", {}).values()) else 1)' <<<"$LIVE_STATUS"; then
    pass "Agent bao 110 user va 9 controlled OVS online"
  else
    fail "LIVE_STATUS khong bao dung 110 user va 9 controlled OVS"
  fi
else
  fail "Control Agent socket khong ton tai"
fi

section "4. CONTROLLER VA OPEN VSWITCH"
ss -H -ltnp 2>/dev/null | grep -E '(^|:)6653[[:space:]]' || true
if ss -H -ltn 2>/dev/null | awk '{print $4}' | grep -Eq '(^|:)6653$'; then
  pass "Controller port 6653 dang listen"
else
  fail "Controller port 6653 khong listen"
fi

echo "--- ovs-vsctl show ---"
sudo ovs-vsctl show
OVS_SHOW_EXIT=$?
echo "EXIT_CODE=$OVS_SHOW_EXIT"
[[ "$OVS_SHOW_EXIT" -eq 0 ]] && pass "ovs-vsctl show" || fail "ovs-vsctl show loi"

EXPECTED_OVS=(
  access_bo access_hq_a access_hq_b access_hq_c access_hq_it
  access_telesale core_hq dist_telesale voice_access
)
mapfile -t ACTUAL_OVS < <(sudo ovs-vsctl list-br | sort)
printf 'ACTUAL_OVS=%s\n' "${ACTUAL_OVS[*]}"
printf 'EXPECTED_OVS=%s\n' "${EXPECTED_OVS[*]}"
if [[ "${ACTUAL_OVS[*]}" == "${EXPECTED_OVS[*]}" ]]; then
  pass "ovs-vsctl co dung 9 OVS, khong co OVS ngoai danh sach"
else
  fail "OVS inventory khong khop danh sach 9 bridge"
fi

for bridge in "${EXPECTED_OVS[@]}"; do
  controller_ref="$(sudo ovs-vsctl --if-exists get Bridge "$bridge" controller 2>/dev/null | tr -d '[]"[:space:]')"
  connected="false"
  if [[ -n "$controller_ref" ]]; then
    connected="$(sudo ovs-vsctl --if-exists get Controller "$controller_ref" is_connected 2>/dev/null | tr -d '[:space:]')"
  fi
  echo "OVS_CONTROLLER bridge=$bridge controller=$controller_ref is_connected=$connected"
  [[ "$connected" == "true" ]] && pass "$bridge ket noi controller" || fail "$bridge chua ket noi controller"
done

for bridge in core_hq dist_telesale; do
  echo "--- ovs-ofctl dump-flows $bridge ---"
  sudo ovs-ofctl -O OpenFlow13 dump-flows "$bridge"
  FLOW_EXIT=$?
  echo "EXIT_CODE=$FLOW_EXIT"
  [[ "$FLOW_EXIT" -eq 0 ]] && pass "Dump flow $bridge" || fail "Khong dump duoc flow $bridge"
done

section "5. RUNTIME INVENTORY VA BUILD TIME"
INVENTORY="$RUNTIME_DIR/phase42_topology_runtime.json"
if [[ -s "$INVENTORY" ]]; then
  cat "$INVENTORY"
  BUILD_SECONDS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["build_duration_seconds"])' "$INVENTORY")"
  echo "BUILD_SECONDS=$BUILD_SECONDS"
  if python3 -c 'import sys; raise SystemExit(0 if float(sys.argv[1]) <= 300 else 1)' "$BUILD_SECONDS"; then
    pass "Build time khong vuot 300 giay"
  else
    fail "Build time vuot 300 giay"
  fi
else
  fail "Khong co phase42_topology_runtime.json"
fi

section "6. RESOURCE SAU KHI BUILD"
free -m
FREE_EXIT=$?
echo "EXIT_CODE=$FREE_EXIT"
swapon --show
SWAP_EXIT=$?
echo "EXIT_CODE=$SWAP_EXIT"
ps -eo pid,ppid,%cpu,%mem,rss,cmd --sort=-rss | sed -n '1,30p'
ps -eo pid,ppid,%cpu,%mem,rss,cmd --sort=-%cpu | sed -n '1,30p'

AVAILABLE_PERCENT="$(free -m | awk '/^Mem:/ {printf "%.2f", ($7/$2)*100}')"
echo "RAM_AVAILABLE_PERCENT=$AVAILABLE_PERCENT"
if python3 -c 'import sys; raise SystemExit(0 if float(sys.argv[1]) >= 15 else 1)' "$AVAILABLE_PERCENT"; then
  pass "RAM available >= 15%"
else
  fail "RAM available duoi 15%"
fi

echo "--- vmstat 1 11 ---"
VMSTAT_OUTPUT="$(vmstat 1 11)"
echo "$VMSTAT_OUTPUT"
VMSTAT_SUMMARY="$(awk 'NR>2 {n++; idle+=$15; if(n==1 || $15<min_idle) min_idle=$15; if(($7+$8)>0) swap_io=1} END {if(n>0) printf "AVG_IDLE=%.2f MIN_IDLE=%.2f PEAK_BUSY=%.2f SWAP_IO=%d", idle/n, min_idle, 100-min_idle, swap_io}' <<<"$VMSTAT_OUTPUT")"
echo "$VMSTAT_SUMMARY"
PEAK_BUSY="$(sed -n 's/.*PEAK_BUSY=\([0-9.]*\).*/\1/p' <<<"$VMSTAT_SUMMARY")"
SWAP_IO="$(sed -n 's/.*SWAP_IO=\([0-9]*\).*/\1/p' <<<"$VMSTAT_SUMMARY")"
if [[ -n "$PEAK_BUSY" ]] && python3 -c 'import sys; raise SystemExit(0 if float(sys.argv[1]) <= 90 else 1)' "$PEAK_BUSY"; then
  pass "CPU peak busy <= 90% trong mau 10 giay"
else
  fail "CPU peak busy vuot 90% hoac khong doc duoc"
fi
[[ "$SWAP_IO" == "0" ]] && pass "Khong co swap-in/swap-out trong mau" || fail "Phat hien swap thrashing"

section "7. KET LUAN"
echo "TOTAL_FAILURES=$FAILURES"
if [[ "$FAILURES" -eq 0 ]]; then
  echo "UBUNTU RESOURCE GATE PASSED."
  exit 0
fi

echo "PHASE BLOCKED: Ubuntu resource gate co $FAILURES loi."
exit 1
