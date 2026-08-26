#!/usr/bin/env python3
"""Execute commands inside the Ubuntu VMware virtual machine via vmrun and capture output."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

VMRUN_PATH = r"C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe"
VMX_PATH = r"D:\Project\CCH_Network_redesign\ubuntu\CCH.vmx"
if not Path(VMX_PATH).exists():
    VMX_PATH = r"D:\HK5\Project\CCH_Network_redesign\ubuntu\CCH.vmx"

VM_USER = "huy"
VM_PASS = "123"


def run_vm_command(script_content: str, timeout: int = 180) -> tuple[int, str]:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, suffix=".sh") as tmp:
        tmp_name = tmp.name
        tmp.write("#!/bin/bash\n")
        tmp.write(f"echo '{VM_PASS}' | sudo -S -v 2>/dev/null || true\n")
        tmp.write("exec > /tmp/vm_run.log 2>&1\n")
        tmp.write(script_content + "\n")

    host_log = Path(tempfile.gettempdir()) / "vm_run_host.log"
    if host_log.exists():
        host_log.unlink()

    try:
        # Copy script into guest
        subprocess.run(
            [VMRUN_PATH, "-gu", VM_USER, "-gp", VM_PASS, "copyFileFromHostToGuest", VMX_PATH, tmp_name, "/tmp/vm_run.sh"],
            check=True,
            capture_output=True,
        )
        # Execute script in guest
        proc = subprocess.run(
            [VMRUN_PATH, "-gu", VM_USER, "-gp", VM_PASS, "runProgramInGuest", VMX_PATH, "/bin/bash", "/tmp/vm_run.sh"],
            capture_output=True,
            timeout=timeout,
        )
        # Copy log back with retries
        output = ""
        for _ in range(5):
            cp_res = subprocess.run(
                [VMRUN_PATH, "-gu", VM_USER, "-gp", VM_PASS, "copyFileFromGuestToHost", VMX_PATH, "/tmp/vm_run.log", str(host_log)],
                capture_output=True,
            )
            if cp_res.returncode == 0:
                break
            time.sleep(1)
        if host_log.exists():
            output = host_log.read_text(encoding="utf-8", errors="replace")
        return proc.returncode, output
    finally:
        Path(tmp_name).unlink(missing_ok=True)
        host_log.unlink(missing_ok=True)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
        if target.exists() and target.is_file():
            if target.suffix == ".py":
                # Copy python script directly to guest
                subprocess.run(
                    [VMRUN_PATH, "-gu", VM_USER, "-gp", VM_PASS, "copyFileFromHostToGuest", VMX_PATH, str(target.resolve()), "/tmp/guest_script.py"],
                    check=True,
                    capture_output=True,
                )
                code, out = run_vm_command("sudo python3 /tmp/guest_script.py\n", timeout=300)
            elif target.suffix == ".sh":
                content = target.read_text(encoding="utf-8")
                code, out = run_vm_command(content, timeout=300)
            else:
                code, out = run_vm_command(" ".join(sys.argv[1:]))
        else:
            code, out = run_vm_command(" ".join(sys.argv[1:]))
    else:
        code, out = run_vm_command("uname -a && whoami")
    print(out)
    sys.exit(code)
