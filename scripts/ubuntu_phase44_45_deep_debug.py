#!/usr/bin/env python3
"""Phase 44/45 Ubuntu runtime diagnostics; never modifies Git or stops services."""
from __future__ import annotations

import argparse, fnmatch, json, os, re, socket, subprocess, sys, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.network_model import build_host_inventory, load_network_model

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "runtime_reports"
API = os.getenv("CCH_API_BASE", "http://127.0.0.1:8000").rstrip("/")
COMMENT = os.getenv("CCH_SOCIAL_DENY_COMMENT", "cch:fw_hq:deny-social-media:hsocial")
EXPECTED_RULES = int(os.getenv("CCH_EXPECTED_FIREWALL_RULE_COUNT", "13"))
EXPECTED_BRIDGES = int(os.getenv("CCH_EXPECTED_OVS_BRIDGES", "8"))
BRANCH_PATTERNS = ("feature/dual-branch-topology", "feature/phase46-automation-docs", "transfer/phase45*", "fix/phase44*", "phase44*")
CONTROL_SOCKET = Path(os.getenv("CCH_MININET_CONTROL_SOCKET", "/tmp/cch_mininet_control.sock"))
CONTROL_TOKEN = os.getenv("CCH_MININET_CONTROL_TOKEN", "cch-local-mininet-token")
TOKEN_FILE = ROOT / "logs" / "operator.token"
os.environ.update({"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONUTF8": "1"})


def cmd(*args: str, timeout: float = 20) -> dict[str, Any]:
    start = time.monotonic()
    try:
        p = subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8", errors="replace",
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
                           check=False, env=os.environ.copy())
        return {"command": list(args), "code": p.returncode, "stdout": p.stdout,
                "stderr": p.stderr, "duration": time.monotonic() - start}
    except subprocess.TimeoutExpired as e:
        return {"command": list(args), "code": 124, "stdout": e.stdout or "",
                "stderr": e.stderr or "", "duration": time.monotonic() - start, "timed_out": True}
    except FileNotFoundError as e:
        return {"command": list(args), "code": 127, "stdout": "", "stderr": str(e),
                "duration": time.monotonic() - start}


def http(method: str, path: str, body: dict[str, Any] | None = None, timeout: float = 20) -> dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json", "X-CCH-Request-ID": uuid.uuid4().hex}
    try:
        operator_token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        operator_token = ""
    if operator_token:
        headers["X-CCH-Operator-Token"] = operator_token
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urlrequest.Request(API + path, data=data, headers=headers, method=method)
    start = time.monotonic()
    try:
        with urlrequest.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try: parsed = json.loads(raw)
            except json.JSONDecodeError: parsed = raw
            return {"status": r.status, "body": parsed, "raw": raw, "duration": time.monotonic() - start}
    except urlerror.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try: parsed = json.loads(raw)
        except json.JSONDecodeError: parsed = raw
        return {"status": e.code, "body": parsed, "raw": raw, "error": str(e), "duration": time.monotonic() - start}
    except (urlerror.URLError, TimeoutError, socket.timeout) as e:
        return {"status": 0, "body": None, "raw": "", "error": str(e), "duration": time.monotonic() - start}


def walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values(): yield from walk(child)
    elif isinstance(value, list):
        for child in value: yield from walk(child)


def first(payload: Any, *names: str) -> Any:
    for node in walk(payload):
        if isinstance(node, dict):
            for name in names:
                if name in node: return node[name]
    return None


def branch_allowed(branch: str) -> bool:
    return bool(branch) and any(fnmatch.fnmatchcase(branch, p) for p in BRANCH_PATTERNS)


def evaluate_checkpoint(repository_available: bool, branch: str, head: str,
                        working_tree_clean: bool | None, ancestor_present: bool | None) -> dict[str, Any]:
    reasons = []
    if not repository_available: reasons.append("REPOSITORY_UNAVAILABLE")
    if not head: reasons.append("HEAD_UNAVAILABLE")
    if working_tree_clean is not True: reasons.append("DIRTY_WORKTREE" if working_tree_clean is False else "WORKTREE_UNKNOWN")
    if not branch_allowed(branch): reasons.append("BRANCH_NOT_ALLOWED")
    if ancestor_present is not True: reasons.append("REQUIRED_ANCESTOR_MISSING" if ancestor_present is False else "ANCESTOR_UNKNOWN")
    return {"repository_available": repository_available, "branch": branch, "head": head,
            "working_tree_clean": working_tree_clean, "allowed_branch_result": branch_allowed(branch),
            "required_ancestor_present": ancestor_present, "final_checkpoint_result": not reasons,
            "failure_reasons": reasons}


def git_state() -> dict[str, Any]:
    branch, head, status = cmd("git", "branch", "--show-current"), cmd("git", "rev-parse", "HEAD"), cmd("git", "status", "--porcelain")
    available = all(x["code"] == 0 for x in (branch, head, status))
    dirty = [x for x in status["stdout"].splitlines() if x.strip()] if status["code"] == 0 else []
    return {"repository_available": available, "branch": branch["stdout"].strip() if branch["code"] == 0 else "",
            "head": head["stdout"].strip() if head["code"] == 0 else "",
            "working_tree_clean": not dirty if status["code"] == 0 else None, "dirty_files": dirty}


def required_ancestor() -> str | None:
    value = os.getenv("CCH_PHASE44_REQUIRED_ANCESTOR", "").strip()
    if value: return value
    r = cmd("git", "log", "--format=%H", "--grep=phase-44-fix: complete firewall policy runtime contracts", "-n", "1")
    return r["stdout"].strip().splitlines()[0] if r["code"] == 0 and r["stdout"].strip() else os.getenv("CCH_PHASE44_FALLBACK_ANCESTOR", "7f382b6")


def ancestor_present(commit: str | None) -> bool | None:
    if not commit: return None
    if cmd("git", "cat-file", "-e", f"{commit}^{{commit}}")["code"] != 0: return False
    return cmd("git", "merge-base", "--is-ancestor", commit, "HEAD")["code"] == 0


def nft_text(firewall: str) -> str:
    return cmd("ip", "netns", "exec", firewall, "nft", "-a", "list", "table", "inet", "cch_filter", timeout=15)["stdout"]


def nft_counter(text: str, exact_comment: str) -> dict[str, Any]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    c = re.compile(r'comment\s+"' + re.escape(exact_comment) + r'"')
    p = re.compile(r'counter\s+packets\s+(\d+)\s+bytes\s+(\d+)')
    for i, line in enumerate(lines):
        if c.search(line):
            m = p.search(line)
            if not m:
                m = p.search(" ".join(lines[i:min(len(lines), i+3)]))
            if m: return {"matched": True, "packets": int(m.group(1)), "bytes": int(m.group(2))}
    return {"matched": False, "packets": None, "bytes": None}


def rule_count(text: str, firewall: str) -> int:
    pattern = re.compile(r'comment\s+"cch:' + re.escape(firewall) + r':')
    return sum(bool(pattern.search(line)) for line in text.replace("\r", "").splitlines())


def api_counter(payload: Any) -> dict[str, Any]:
    for node in walk(payload):
        if isinstance(node, dict) and node.get("comment") == COMMENT and isinstance(node.get("packets"), int):
            return {"matched": True, "packets": node["packets"], "bytes": node.get("bytes", 0)}
    for node in walk(payload):
        if isinstance(node, dict) and (node.get("name") or node.get("id") or node.get("firewall")) == "fw_hq":
            for child in walk(node):
                if isinstance(child, dict) and isinstance(child.get("social_deny"), dict):
                    c = child["social_deny"]
                    if isinstance(c.get("packets"), int): return {"matched": True, "packets": c["packets"], "bytes": c.get("bytes", 0)}
    return {"matched": False, "packets": None, "bytes": None}


def agent_health(payload: Any) -> bool:
    return any(isinstance(n, dict) and (n.get("agent_alive") is True or n.get("status") == "online") for n in walk(payload))



def agent_request(command: str, **payload: Any) -> dict[str, Any]:
    request = {
        "token": CONTROL_TOKEN,
        "command": command,
        "request_id": uuid.uuid4().hex,
        **payload,
    }
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(20)
        client.connect(str(CONTROL_SOCKET))
        client.sendall((json.dumps(request) + "\n").encode("utf-8"))
        chunks = bytearray()
        while b"\n" not in chunks:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.extend(chunk)
    if not chunks:
        raise RuntimeError(f"Control Agent khong tra loi lenh {command}.")
    response = json.loads(bytes(chunks).split(b"\n", 1)[0].decode("utf-8"))
    if not isinstance(response, dict):
        raise RuntimeError(f"Control Agent tra ve response khong hop le cho {command}.")
    return response


class Report:
    def __init__(self, mode: str):
        REPORTS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.log_path = REPORTS / f"ubuntu_phase44_45_debug_{stamp}.log"
        self.json_path = REPORTS / f"ubuntu_phase44_45_debug_{stamp}.json"
        self.data = {"overall_status": "PENDING", "mode": mode, "git": {}, "runtime": {},
                     "firewall_counter": {}, "git_checkpoint": {}, "iperf_concurrency": {}, "errors": []}
        self.lock = threading.Lock()
    def log(self, message: str):
        with self.lock:
            print(message, flush=True)
            with self.log_path.open("a", encoding="utf-8") as f: f.write(message + "\n")
    def finish(self, ok: bool, blocked: bool = False) -> int:
        status = "BLOCKED" if blocked else ("PASS" if ok else "FAIL")
        self.data["overall_status"] = status
        self.json_path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2, default=str) + "\n")
        self.log(f"OVERALL_STATUS={status}"); self.log(f"LOG={self.log_path}"); self.log(f"JSON={self.json_path}")
        return 0 if ok else 1


def diagnose(r: Report) -> bool:
    g = git_state(); bridges = [x for x in cmd("ovs-vsctl", "list-br", timeout=10)["stdout"].splitlines() if x.strip()]
    processes = cmd("bash", "-lc", "pgrep -af '[t]opology_hybrid_sdn.py|[o]sken-manager|[c]ontroller_policy.py|[u]vicorn|[v]ite' || true")["stdout"].splitlines()
    namespaces = [x.split()[0] for x in cmd("ip", "netns", "list", timeout=10)["stdout"].splitlines() if x.strip()]
    health = http("GET", "/api/health", timeout=5)
    runtime = {"processes": processes, "ovs_bridges": bridges, "ovs_bridge_count": len(bridges),
               "namespaces": namespaces, "backend_health_http": health["status"], "agent_healthy": agent_health(health["body"]),
               "mininet_socket": Path("/tmp/cch_mininet_control.sock").is_socket(), "osken_socket": Path("/tmp/cch_osken_admin.sock").is_socket()}
    r.data["git"], r.data["runtime"] = g, runtime; r.log(json.dumps({"git": g, "runtime": runtime}, indent=2))
    return any("topology_hybrid_sdn.py" in x for x in processes) and any("osken-manager" in x or "controller_policy.py" in x for x in processes) and len(bridges) == EXPECTED_BRIDGES and health["status"] == 200 and runtime["agent_healthy"]


def firewall_case(r: Report) -> bool:
    before_raw = nft_text("fw_hq"); before_api = http("GET", "/api/firewalls", timeout=10)
    braw, bapi = nft_counter(before_raw, COMMENT), api_counter(before_api["body"])
    ping = http("POST", "/api/test/ping", {"source": "h20_01", "destination": "hsocial"}, timeout=15)
    hosts = build_host_inventory(load_network_model())
    runtime_probe = agent_request(
        "PING",
        source="h20_01",
        destination_ip=hosts["hsocial"]["ip"],
        count=3,
    )
    after_raw = nft_text("fw_hq"); after_api = http("GET", "/api/firewalls", timeout=10)
    araw, aapi = nft_counter(after_raw, COMMENT), api_counter(after_api["body"])
    raw_delta = None if braw["packets"] is None or araw["packets"] is None else araw["packets"] - braw["packets"]
    api_delta = None if bapi["packets"] is None or aapi["packets"] is None else aapi["packets"] - bapi["packets"]
    action, blocked = first(ping["body"], "action"), first(ping["body"], "blocked_at")
    api_policy_ok = (
        ping["status"] == 200
        and first(ping["body"], "error_code") == "POLICY_DENIED"
        and action == "deny"
        and blocked == "fw_hq"
    )
    runtime_probe_ok = runtime_probe.get("error_code") is None and runtime_probe.get("ok") is False
    count = rule_count(after_raw, "fw_hq")
    result = {"raw_delta": raw_delta, "api_delta": api_delta, "rule_count": count, "expected_rule_count": EXPECTED_RULES,
              "policy_action": action, "blocked_at": blocked, "api_policy_contract": api_policy_ok,
              "runtime_probe": {"ok": runtime_probe.get("ok"), "error_code": runtime_probe.get("error_code"),
                                "raw_tail": str(runtime_probe.get("raw") or "")[-500:]},
              "runtime_probe_contract": runtime_probe_ok, "raw_before": braw, "raw_after": araw,
              "api_before": bapi, "api_after": aapi}
    ok = raw_delta is not None and raw_delta > 0 and api_delta == raw_delta and count == EXPECTED_RULES and api_policy_ok and runtime_probe_ok
    result["status"] = "PASS" if ok else "FAIL"; r.data["firewall_counter"] = result
    r.log(json.dumps(result, indent=2)); r.log(f"raw delta = {raw_delta}"); r.log(f"api delta = {api_delta}"); r.log(f"rule_count = {count}"); r.log(f"expected_rule_count = {EXPECTED_RULES}"); r.log(f"policy action = {action}"); r.log(f"blocked_at = {blocked}")
    return ok


def git_case(r: Report) -> tuple[bool, bool]:
    g = git_state(); ancestor = required_ancestor(); present = ancestor_present(ancestor)
    result = evaluate_checkpoint(g["repository_available"], g["branch"], g["head"], g["working_tree_clean"], present)
    result.update({"required_ancestor": ancestor, "dirty_files": g["dirty_files"]}); r.data["git_checkpoint"] = result
    r.log(json.dumps(result, indent=2)); r.log(f"branch={g['branch']}"); r.log(f"HEAD={g['head']}"); r.log(f"working_tree_clean={g['working_tree_clean']}"); r.log(f"required ancestor={ancestor}"); r.log(f"ancestor check result={present}"); r.log(f"allowed branch result={result['allowed_branch_result']}"); r.log(f"final checkpoint result={result['final_checkpoint_result']}"); r.log(f"exact failure reason={','.join(result['failure_reasons']) or 'NONE'}")
    return result["final_checkpoint_result"], g["working_tree_clean"] is False


def throughput(payload: Any) -> float | None:
    value = first(payload, "throughput_mbps", "mbps", "bits_per_second", "bps")
    if not isinstance(value, (int, float)): return None
    return float(value) / 1_000_000 if value > 10000 else float(value)


def iperf_request(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    start = time.monotonic(); response = http("POST", "/api/test/iperf", payload, timeout=20); end = time.monotonic(); body = response["body"] if isinstance(response["body"], dict) else {}
    return {"name": name, "start": start, "end": end, "http_status": response["status"], "ok": body.get("ok"),
            "error_code": first(body, "error_code"), "throughput_mbps": throughput(body), "response": body}


def iperf_case(r: Report) -> bool:
    seconds = int(os.getenv("CCH_IPERF_SECONDS", "5")); before = cmd("pgrep", "-af", "[i]perf3")["stdout"].splitlines()
    a = {"source": "h20_01", "destination": "h90", "protocol": "tcp", "seconds": seconds}; b = {"source": "h50_01", "destination": "hcall", "protocol": "tcp", "seconds": seconds}
    with ThreadPoolExecutor(max_workers=2) as pool: different = [pool.submit(iperf_request, "different_A", a), pool.submit(iperf_request, "different_B", b)]; different = [x.result() for x in different]
    overlap = max(0.0, min(x["end"] for x in different) - max(x["start"] for x in different))
    different_ok = overlap > 0 and all(x["http_status"] == 200 and x["ok"] is True and isinstance(x["throughput_mbps"], float) and x["throughput_mbps"] > 0 and x["error_code"] not in {"IPERF_PARSE_FAILED", "IPERF_CLIENT_TIMEOUT"} for x in different)
    same_a = {"source": "h20_01", "destination": "h90", "protocol": "tcp", "seconds": seconds}; same_b = {"source": "h30_01", "destination": "h90", "protocol": "tcp", "seconds": seconds}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(iperf_request, "same_first", same_a); deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not first_future.done():
            sessions = http("GET", "/api/live/iperf-sessions", timeout=3)
            if sessions["status"] == 200 and "h90" in sessions["raw"]: break
            time.sleep(.1)
        second = iperf_request("same_second", same_b); first_result = first_future.result()
    same_ok = first_result["http_status"] == 200 and second["http_status"] == 409 and second["error_code"] == "IPERF_BUSY"
    health = http("GET", "/api/health", timeout=5); healthy = health["status"] == 200 and agent_health(health["body"])
    after = cmd("pgrep", "-af", "[i]perf3")["stdout"].splitlines(); orphans = sorted(set(after) - set(before))
    result = {"different_destinations": different, "overlap_duration": overlap, "different_destinations_pass": different_ok,
              "same_destination": {"first": first_result, "second": second}, "same_destination_pass": same_ok,
              "agent_HEALTH": healthy, "new_orphan_iperf3": orphans}
    ok = different_ok and same_ok and healthy and not orphans; result["status"] = "PASS" if ok else "FAIL"; r.data["iperf_concurrency"] = result
    r.log(json.dumps(result, indent=2, default=str)); r.log(f"overlap duration = {overlap}"); r.log(f"same destination HTTP 409 error_code={second['error_code']}"); r.log(f"agent HEALTH={healthy}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Ubuntu Phase 44/45 deep diagnostics")
    sub = parser.add_subparsers(dest="command", required=True); sub.add_parser("diagnose"); sub.add_parser("verify")
    one = sub.add_parser("run-case"); one.add_argument("case", choices=("firewall-counter", "git-checkpoint", "iperf-concurrency")); args = parser.parse_args(); report = Report(args.command)
    if args.command == "diagnose": return report.finish(diagnose(report))
    if args.command == "run-case":
        if args.case == "firewall-counter": return report.finish(firewall_case(report))
        if args.case == "git-checkpoint":
            ok, dirty = git_case(report); return report.finish(ok, dirty)
        return report.finish(iperf_case(report))
    if not diagnose(report): return report.finish(False)
    if not firewall_case(report): return report.finish(False)
    ok, dirty = git_case(report)
    if not ok: return report.finish(False, dirty)
    return report.finish(iperf_case(report))


if __name__ == "__main__": raise SystemExit(main())
