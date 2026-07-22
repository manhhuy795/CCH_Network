#!/usr/bin/env python3
"""Phase 46 automation, documentation and Ubuntu runtime gate."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
EXPECTED_BRIDGES = ("access_hq_a", "access_hq_b", "access_hq_c", "access_hq_it", "voice_access", "core_hq", "access_telesale", "dist_telesale", "access_bo")
REQUIRED_DOCS = ("docs/architecture.md", "docs/installation_ubuntu.md", "docs/runtime_operations.md", "docs/troubleshooting.md", "docs/testing_and_acceptance.md", "docs/security_notes.md")
REQUIRED_SCRIPTS = ("scripts/start_demo.sh", "scripts/stop_demo.sh", "scripts/check_demo_health.sh", "scripts/phase46_automation_docs_gate.sh")
SECRET_PATTERNS = (re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"), re.compile(r"(?i)\\bpassword\\s*[:=]\\s*[A-Za-z0-9+/=_-]{16,}"), re.compile(r"CCH_DASHBOARD_OPERATOR_TOKEN\\s*=\\s*[A-Za-z0-9_-]{20,}"))


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def redact(value: str, secrets: Iterable[str] = ()) -> str:
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value


def command_available(command: str, environ: dict[str, str] | None = None) -> bool:
    current = (environ or os.environ).get("PATH", "")
    search_path = current + os.pathsep + "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    return shutil.which(command, path=search_path) is not None


def select_osken_python(root: Path = ROOT_DIR) -> Path | None:
    candidates = (root / "sdn_mpls_demo/.venv/bin/python", root / ".venv/bin/python", Path("/usr/bin/python3"))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK) and python_is_compatible(candidate)[0]:
            result = subprocess.run([str(candidate), "-c", "import os_ken"], capture_output=True, check=False)
            if result.returncode == 0:
                return candidate
    return None


def python_is_compatible(path: str | Path, minimum: tuple[int, int] = (3, 10)) -> tuple[bool, str]:
    try:
        result = subprocess.run([str(path), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    version = result.stdout.strip()
    if result.returncode != 0:
        return False, result.stderr.strip()
    try:
        major, minor = (int(part) for part in version.split(".", 1))
    except ValueError:
        return False, f"invalid-version:{version}"
    return (major, minor) >= minimum, version


def select_python(root: Path = ROOT_DIR) -> Path | None:
    candidates = [Path(os.environ["CCH_PHASE46_PYTHON_BIN"])] if os.environ.get("CCH_PHASE46_PYTHON_BIN") else []
    candidates += [root / ".venv/bin/python", root / "dashboard/backend/.venv/bin/python", root / "sdn_mpls_demo/.venv/bin/python", Path(sys.executable), Path("/usr/bin/python3")]
    return next((path for path in candidates if path.is_file() and os.access(path, os.X_OK) and python_is_compatible(path)[0]), None)


def parse_listening_ports(value: str) -> set[int]:
    ports = set()
    for line in value.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[3].rsplit(":", 1)[-1].isdigit():
            ports.add(int(fields[3].rsplit(":", 1)[-1]))
    return ports


def is_stale_socket(path: Path, token: str, timeout: float = 1.5) -> bool:
    if not path.exists():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(path))
            client.sendall((json.dumps({"token": token, "command": "HEALTH"}) + "\n").encode())
            payload = json.loads(client.recv(65536).split(b"\n", 1)[0].decode())
        return not (isinstance(payload, dict) and payload.get("ok") is True and payload.get("agent_alive") is True)
    except (OSError, ValueError, json.JSONDecodeError):
        return True


def safe_stop(processes: Iterable[subprocess.Popen[str]]) -> list[int]:
    stopped = []
    for process in processes:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            stopped.append(process.pid)
    return stopped


def docs_reference_errors(root: Path) -> list[str]:
    errors = []
    pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for document in sorted(root.glob("docs/**/*.md")):
        for target in pattern.findall(document.read_text(encoding="utf-8")):
            target = target.split("#", 1)[0].strip()
            if target and "://" not in target and not target.startswith("mailto:") and not (document.parent / target).resolve().exists():
                errors.append(f"{document.relative_to(root)} -> {target}")
    return errors


def secret_scan(root: Path) -> list[str]:
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=False)
    if result.returncode:
        return [result.stderr.decode(errors="replace")]
    matches = []
    for raw in result.stdout.split(b"\\0"):
        if not raw:
            continue
        path = root / os.fsdecode(raw)
        if path.is_file():
            try:
                value = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if any(pattern.search(value) for pattern in SECRET_PATTERNS):
                matches.append(str(path.relative_to(root)))
    return sorted(set(matches))


def summary_payload(mode: str, branch: str, head: str, cases: list[dict[str, Any]], report_dir: Path) -> dict[str, Any]:
    failed = [case for case in cases if case["status"] in {"FAIL", "BLOCKED"}]
    return {"schema_version": 1, "suite": "phase46_automation_docs", "mode": mode, "overall_status": "PASS" if not failed else ("FAIL" if any(case["status"] == "FAIL" for case in failed) else "BLOCKED"), "checked_at": datetime.now(timezone.utc).isoformat(), "branch": branch, "head": head, "first_failure": failed[0] if failed else None, "cases": cases, "report_directory": str(report_dir), "token_policy": "tokens are redacted and never stored in artifacts"}


class Gate:
    def __init__(self, args: argparse.Namespace) -> None:
        raw = Path(args.report_dir) if args.report_dir else Path("runtime_reports") / f"phase46_automation_docs_{utc_stamp()}"
        self.args = args
        self.report_dir = (raw if raw.is_absolute() else ROOT_DIR / raw).resolve()
        self.report_dir.mkdir(parents=True, exist_ok=True)
        (self.report_dir / "cases").mkdir(exist_ok=True)
        self.cases: list[dict[str, Any]] = []
        self.started: list[subprocess.Popen[str]] = []
        self.secrets = self.read_secrets()
        self.python = select_python()
        self.branch = self.git(["branch", "--show-current"]).strip()
        self.head = self.git(["rev-parse", "--short", "HEAD"]).strip()
        self.inventory()

    def read_secrets(self) -> list[str]:
        try:
            value = (ROOT_DIR / "logs/operator.token").read_text(encoding="utf-8").strip()
        except OSError:
            value = ""
        return [value] if value else []

    def git(self, args: Sequence[str]) -> str:
        result = subprocess.run(["git", "-C", str(ROOT_DIR), *args], capture_output=True, text=True, check=False)
        return redact((result.stdout + result.stderr).strip(), self.secrets)

    def inventory(self) -> None:
        status = self.git(["status", "--short", "--branch"])
        (self.report_dir / "baseline.log").write_text(f"checked_at={datetime.now(timezone.utc).isoformat()}\nbranch={self.branch}\nhead={self.head}\n{status}\n", encoding="utf-8")
        tracked = self.git(["ls-files"]).splitlines()
        (self.report_dir / "project_inventory.md").write_text("# Project inventory\n\nIdentity: Hybrid MPLS L3VPN + SDN Edge Policy Demo cho Call Center BPO.\n\n" + "\n".join(f"- {item}" for item in tracked if item) + "\n", encoding="utf-8")
        (self.report_dir / "automation_inventory.md").write_text("# Automation inventory\n\n" + "\n".join(f"- {item}" for item in REQUIRED_SCRIPTS) + "\n", encoding="utf-8")
        docs = sorted(path.relative_to(ROOT_DIR).as_posix() for path in ROOT_DIR.glob("docs/**/*.md"))
        (self.report_dir / "documentation_inventory.md").write_text("# Documentation inventory\n\n" + "\n".join(f"- {item}" for item in docs) + "\n", encoding="utf-8")
        (self.report_dir / "files_changed.txt").write_text(status + "\n", encoding="utf-8")

    def record(self, name: str, status: str, *, exit_code: int = 0, reason: str = "", summary: Any = None, duration: float = 0.0) -> bool:
        case = {"name": name, "status": status, "exit_code": exit_code, "duration_seconds": round(duration, 3), "error_code": reason or None, "response_summary": summary}
        self.cases.append(case)
        if self.args.verbose:
            print(f"{status:<7} {name} {json.dumps(case, ensure_ascii=False)}", flush=True)
        return status == "PASS"

    def value(self, name: str, passed: bool, *, reason: str = "", summary: Any = None, blocked: bool = False) -> bool:
        return self.record(name, "PASS" if passed else ("BLOCKED" if blocked else "FAIL"), reason=reason if not passed else "", summary=summary)

    def command(self, name: str, argv: Sequence[str], *, timeout: float = 120, cwd: Path = ROOT_DIR, log_name: str | None = None, allow_blocked: bool = False) -> bool:
        started = time.monotonic()
        try:
            result = subprocess.run(list(argv), cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
            stdout, stderr = redact(result.stdout, self.secrets), redact(result.stderr, self.secrets)
            status = "PASS" if result.returncode == 0 else ("BLOCKED" if allow_blocked else "FAIL")
            name = log_name or name
            (self.report_dir / "cases" / f"{name}.stdout").write_text(stdout, encoding="utf-8")
            (self.report_dir / "cases" / f"{name}.stderr").write_text(stderr, encoding="utf-8")
            return self.record(name, status, exit_code=result.returncode, reason="" if result.returncode == 0 else f"EXIT_CODE_{result.returncode}", summary={"command": list(argv), "stdout_tail": stdout[-1200:], "stderr_tail": stderr[-1200:]}, duration=time.monotonic() - started)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return self.record(name, "BLOCKED" if allow_blocked else "FAIL", exit_code=124 if isinstance(exc, subprocess.TimeoutExpired) else 127, reason=type(exc).__name__, summary=str(exc), duration=time.monotonic() - started)

    def port_open(self, port: int) -> bool:
        return port in parse_listening_ports(subprocess.run(["ss", "-ltnH"], capture_output=True, text=True, check=False).stdout)

    def health(self) -> tuple[bool, dict[str, Any]]:
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=5) as response:
                payload = json.loads(response.read().decode())
            return response.status == 200, payload
        except Exception as exc:
            return False, {"error_code": type(exc).__name__, "detail": str(exc)}

    def agent(self, command: str) -> dict[str, Any]:
        path = Path(os.environ.get("CCH_MININET_CONTROL_SOCKET", "/tmp/cch_mininet_control.sock"))
        token = os.environ.get("CCH_MININET_CONTROL_TOKEN", "cch-local-mininet-token")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(10)
            client.connect(str(path))
            client.sendall((json.dumps({"token": token, "command": command}) + "\n").encode())
            payload = client.recv(65536)
        return json.loads(payload.split(b"\n", 1)[0].decode())

    def preflight(self) -> bool:
        ok = self.value("linux_platform", platform.system() == "Linux", reason="LINUX_REQUIRED", blocked=platform.system() != "Linux")
        ok &= self.value("python_compatible", self.python is not None, reason="PYTHON_REQUIRED", blocked=self.python is None)
        for command in ("git", "curl", "ss", "node", "npm", "mn", "ovs-vsctl", "ovs-ofctl"):
            available = command_available(command)
            ok &= self.value(f"dependency_{command}", available, reason=f"MISSING_{command}", blocked=not available)
        osken_python = select_osken_python()
        imported = osken_python is not None
        ok &= self.value("osken_import", imported, reason="OSKEN_UNAVAILABLE", summary={"python": str(osken_python) if osken_python else None}, blocked=not imported)
        controller = self.port_open(6653)
        ok &= self.value("controller_port", controller, reason="CONTROLLER_OFFLINE", blocked=not controller)
        health_ok, payload = self.health() if self.port_open(8000) else (False, {"error_code": "BACKEND_OFFLINE"})
        ok &= self.value("backend_health", health_ok and payload.get("status") in {"online", "degraded"}, reason="BACKEND_UNHEALTHY", summary=payload, blocked=not health_ok)
        path = Path(os.environ.get("CCH_MININET_CONTROL_SOCKET", "/tmp/cch_mininet_control.sock"))
        stale = is_stale_socket(path, os.environ.get("CCH_MININET_CONTROL_TOKEN", "cch-local-mininet-token")) if path.exists() else True
        ok &= self.value("control_socket", not stale, reason="AGENT_STALE_SOCKET" if path.exists() else "AGENT_NOT_READY", blocked=True if stale else False)
        if self.args.reuse_running:
            running = controller and self.port_open(8000) and self.port_open(5173)
            ok &= self.value("healthy_reuse", running, reason="RUNTIME_NOT_READY", blocked=not running)
        else:
            self.value("healthy_reuse", False, reason="REUSE_FLAG_NOT_SET", blocked=True)
        return bool(ok)

    def docs(self) -> bool:
        ok = True
        for relative in REQUIRED_DOCS:
            ok &= self.value(f"doc_{Path(relative).stem}", (ROOT_DIR / relative).is_file(), reason=f"MISSING_{relative}")
        errors = docs_reference_errors(ROOT_DIR)
        return bool(ok and self.value("docs_references", not errors, reason="BROKEN_DOC_REFERENCE", summary={"errors": errors}))

    def static(self) -> bool:
        if not self.python:
            return self.value("static_python", False, reason="PYTHON_REQUIRED", blocked=True)
        python_files = []
        for source_root in ("scripts", "sdn_mpls_demo", "dashboard/backend"):
            python_files.extend(path for path in (ROOT_DIR / source_root).rglob("*.py") if ".venv" not in path.parts and "site-packages" not in path.parts)
        ok = self.command("py_compile", [str(self.python), "-m", "py_compile", *[str(path) for path in sorted(python_files)]], timeout=120)
        for path in sorted(ROOT_DIR.glob("scripts/*.sh")) + sorted((ROOT_DIR / "sdn_mpls_demo").glob("*.sh")):
            ok &= self.command(f"bash_n_{path.name}", ["bash", "-n", str(path)], timeout=30)
        ok &= self.command("pytest_collection", [str(self.python), "-m", "pytest", "--collect-only", "-q"], timeout=180)
        ok &= self.command("pytest_phase46", [str(self.python), "-m", "pytest", "-q", "tests/test_phase46_automation_docs.py"], timeout=180)
        ok &= self.command("pytest_full", [str(self.python), "-m", "pytest", "-q"], timeout=300)
        ok &= self.command("git_diff_check", ["git", "-C", str(ROOT_DIR), "diff", "--check"], timeout=30)
        matches = secret_scan(ROOT_DIR)
        ok &= self.value("secret_scan", not matches, reason="SECRET_PATTERN_FOUND", summary={"files": matches})
        ok &= self.docs()
        frontend = ROOT_DIR / "dashboard/frontend"
        if command_available("npm") and (frontend / "package-lock.json").is_file():
            ok &= self.command("frontend_npm_ci", ["npm", "ci"], cwd=frontend, timeout=600)
            frontend_build_ok = self.command("frontend_build", ["npm", "run", "build"], cwd=frontend, timeout=300)
            build_stdout_path = self.report_dir / "cases" / "frontend_build.stdout"
            build_stderr_path = self.report_dir / "cases" / "frontend_build.stderr"
            build_stdout = build_stdout_path.read_text(encoding="utf-8") if build_stdout_path.exists() else ""
            build_stderr = build_stderr_path.read_text(encoding="utf-8") if build_stderr_path.exists() else ""
            (self.report_dir / "frontend_build.log").write_text(
                "COMMAND: npm run build\n--- STDOUT ---\n"
                + build_stdout
                + "\n--- STDERR ---\n"
                + build_stderr,
                encoding="utf-8",
            )
            ok &= frontend_build_ok
        else:
            ok &= self.value("frontend_build", False, reason="FRONTEND_DEPENDENCY_MISSING", blocked=True)
        (self.report_dir / "static_validation.log").write_text("\n".join(f"{c['status']} {c['name']}" for c in self.cases) + "\n", encoding="utf-8")
        return bool(ok)

    def clean_clone(self) -> tuple[bool, dict[str, Any]]:
        origin = self.git(["remote", "get-url", "origin"]).splitlines()[0]
        destination = Path(tempfile.mkdtemp(prefix=f"CCH_Network_phase46_clean_{utc_stamp()}_", dir="/tmp"))
        result = subprocess.run(["git", "clone", "--quiet", "--branch", self.branch, origin, str(destination)], capture_output=True, text=True, check=False)
        if result.returncode:
            return False, {"error_code": "CLONE_FAILED", "stderr": redact(result.stderr, self.secrets)}
        forbidden = [destination / item for item in (".venv", "dashboard/frontend/node_modules", "sdn_mpls_demo/.venv")] + list(destination.glob("**/operator.token"))
        python = select_python(destination)
        syntax = bool(python) and subprocess.run([str(python), "-m", "compileall", "-q", "scripts", "sdn_mpls_demo", "dashboard/backend"], cwd=destination, check=False).returncode == 0
        missing = [str(item) for item in forbidden if item.exists()]
        return not missing and not docs_reference_errors(destination) and syntax, {"clone": str(destination), "forbidden_present": missing, "syntax_ok": syntax}

    def automation(self) -> bool:
        if not self.python:
            return self.value("automation_python", False, reason="PYTHON_REQUIRED", blocked=True)
        ok = self.command("validate_vars", [str(self.python), "scripts/validate_vars.py"], timeout=120)
        ok &= self.command("verify_network", [str(self.python), "scripts/verify_network.py"], timeout=120)
        for script in REQUIRED_SCRIPTS:
            path = ROOT_DIR / script
            ok &= self.value(f"script_{Path(script).stem}", path.is_file() and os.access(path, os.X_OK), reason=f"MISSING_OR_NOT_EXECUTABLE_{script}")
        clone_ok, summary = self.clean_clone()
        return bool(ok and self.value("clean_clone_check", clone_ok, reason="CLEAN_CLONE_FAILED", summary=summary, blocked=not clone_ok))

    def runtime(self) -> bool:
        runtime_case_start = len(self.cases)
        if platform.system() != "Linux" or os.geteuid() != 0:
            return self.value("runtime_privilege", False, reason="LINUX_ROOT_REQUIRED", blocked=True)
        if not self.args.reuse_running and not self.args.start_missing:
            return self.value("runtime_start_mode", False, reason="EXPLICIT_REUSE_OR_START_REQUIRED", blocked=True)
        ok = True
        for label, port, error in (("controller", 6653, "CONTROLLER_OFFLINE"), ("backend", 8000, "BACKEND_OFFLINE"), ("frontend", 5173, "FRONTEND_OFFLINE")):
            ok &= self.value(f"port_{label}", self.port_open(port), reason=error, blocked=True)
        bridges = tuple(x for x in subprocess.run(["ovs-vsctl", "list-br"], capture_output=True, text=True, check=False).stdout.splitlines() if x)
        ok &= self.value("ovs_bridge_inventory", set(bridges) == set(EXPECTED_BRIDGES), reason="OVS_BRIDGE_INVENTORY_MISMATCH", summary={"expected": EXPECTED_BRIDGES, "actual": bridges})
        if set(bridges) == set(EXPECTED_BRIDGES):
            for switch in EXPECTED_BRIDGES:
                result = subprocess.run(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", switch], capture_output=True, text=True, check=False)
                ok &= self.value(f"flows_{switch}", result.returncode == 0 and "actions=" in result.stdout, reason="OPENFLOW_UNAVAILABLE")
        try:
            health = self.agent("HEALTH")
            ok &= self.value("agent_health", health.get("ok") is True and health.get("agent_alive") is True, reason="AGENT_NOT_READY")
            live = self.agent("LIVE_STATUS")
            ok &= self.value("host_count", live.get("user_hosts_online") == 110, reason="HOST_COUNT_MISMATCH", summary=live)
        except Exception as exc:
            ok &= self.value("agent_health", False, reason="AGENT_TIMEOUT", summary={"detail": str(exc)}, blocked=True)
        names = {line.split()[0] for line in subprocess.run(["ip", "netns", "list"], capture_output=True, text=True, check=False).stdout.splitlines() if line.split()}
        ok &= self.value("firewall_namespaces", {"fw_hq", "fw_telesale"} <= names, reason="FIREWALL_NAMESPACE_MISSING")
        orphan = subprocess.run(["pgrep", "-af", "[i]perf3"], capture_output=True, text=True, check=False)
        ok &= self.value("no_iperf_orphans", orphan.returncode != 0, reason="IPERF_ORPHAN_PRESENT")
        if self.python:
            ok &= self.command("phase44_firewall_runtime", [str(self.python), "scripts/phase44_firewall_runtime_check.py"], timeout=600)
            ok &= self.command("dashboard_runtime_smoke", [str(self.python), "scripts/dashboard_runtime_smoke_test.py"], timeout=900)
            ok &= self.command("phase44_45_combined", ["bash", "scripts/phase44_45_combined_acceptance.sh"], timeout=1200)
        runtime_cases = self.cases[runtime_case_start:]
        runtime_lines = [
            "Phase 46 runtime validation",
            f"checked_at={datetime.now(timezone.utc).isoformat()}",
        ]
        for case in runtime_cases:
            runtime_lines.append(json.dumps(case, ensure_ascii=False))
        (self.report_dir / "runtime_validation.log").write_text("\n".join(runtime_lines) + "\n", encoding="utf-8")
        regression_names = {"phase44_firewall_runtime", "dashboard_runtime_smoke", "phase44_45_combined"}
        regression_lines = [
            "Phase 44/45 regression validation",
            f"checked_at={datetime.now(timezone.utc).isoformat()}",
        ]
        for case in runtime_cases:
            if case["name"] in regression_names:
                regression_lines.append(json.dumps(case, ensure_ascii=False))
                for suffix in ("stdout", "stderr"):
                    case_path = self.report_dir / "cases" / f"{case['name']}.{suffix}"
                    if case_path.exists():
                        regression_lines.append(f"--- {case['name']}.{suffix} ---")
                        regression_lines.append(case_path.read_text(encoding="utf-8"))
        (self.report_dir / "phase44_45_regression.log").write_text("\n".join(regression_lines) + "\n", encoding="utf-8")
        return bool(ok)

    def artifacts(self) -> bool:
        leaked = []
        for path in self.report_dir.rglob("*"):
            if path.is_file():
                try:
                    value = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                if path.name == "operator.token" or any(secret and secret in value for secret in self.secrets):
                    leaked.append(str(path))
        return self.value("artifact_secret_exclusion", not leaked, reason="SECRET_IN_ARTIFACT", summary={"files": leaked})

    def run(self, modes: Sequence[str]) -> int:
        try:
            for index, mode in enumerate(modes):
                getattr(self, mode)()
                if any(c["status"] in {"FAIL", "BLOCKED"} for c in self.cases) and index < len(modes) - 1:
                    for skipped in modes[index + 1:]:
                        self.value(f"mode_{skipped}_skipped", False, reason="FIRST_FAILURE_GATING", blocked=True)
                    break
            self.artifacts()
        finally:
            safe_stop(self.started)
            payload = summary_payload(",".join(modes), self.branch, self.head, self.cases, self.report_dir)
            (self.report_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (self.report_dir / "files_changed.txt").write_text(self.git(["status", "--short"]) + "\n", encoding="utf-8")
            if payload["overall_status"] != "PASS":
                first = payload.get("first_failure") or {}
                (self.report_dir / "NEXT_ACTION.md").write_text(f"# NEXT ACTION\n\nFirst failure: {first.get('name', 'unknown')}\nReason: {first.get('error_code', 'unknown')}\n", encoding="utf-8")
        statuses = {c["status"] for c in self.cases}
        return 1 if "FAIL" in statuses else (3 if "BLOCKED" in statuses else 0)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 46 automation, documentation and Ubuntu runtime gate")
    parser.add_argument("mode", choices=("preflight", "static", "automation", "docs", "runtime", "all"))
    parser.add_argument("--reuse-running", action="store_true")
    parser.add_argument("--start-missing", action="store_true")
    parser.add_argument("--report-dir")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    modes = ("preflight", "static", "automation", "docs", "runtime") if args.mode == "all" else (args.mode,)
    return Gate(args).run(modes)


if __name__ == "__main__":
    raise SystemExit(main())

