from __future__ import annotations

import shutil
import subprocess


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run_command(command: list[str], timeout: int = 20) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, output.strip()
    except FileNotFoundError:
        return False, f"Khong tim thay lenh {command[0]}. Hay cai Mininet/OVS/iperf3 truoc."
    except subprocess.TimeoutExpired:
        return False, "Lenh bi timeout. Hay kiem tra topology Mininet co dang chay khong."


def mininet_hint() -> str:
    if not command_exists("ovs-vsctl"):
        return "Open vSwitch chua san sang tren may nay."
    return "Neu test that bai, hay chay controller va topology Mininet truoc."

