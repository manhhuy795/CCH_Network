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
        return False, f"Không tìm thấy lệnh {command[0]}. Hãy cài Mininet/OVS/iperf3 trước."
    except subprocess.TimeoutExpired:
        return False, "Lệnh bị quá thời gian. Hãy kiểm tra topology Mininet có đang chạy không."


def mininet_hint() -> str:
    if not command_exists("ovs-vsctl"):
        return "Open vSwitch chưa sẵn sàng trên máy này."
    return "Nếu test thất bại, hãy chạy controller và topology Mininet trước."
