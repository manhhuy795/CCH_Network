import subprocess
import sys
from pathlib import Path

VMRUN_PATH = r"C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe"
VMX_PATH = r"D:\HK5\Project\CCH_Network_redesign\ubuntu\CCH.vmx"
VM_USER = "huy"
VM_PASS = "123"

def copy_to_vm(host_path: str, guest_path: str):
    res = subprocess.run(
        [VMRUN_PATH, "-gu", VM_USER, "-gp", VM_PASS, "CopyFileFromHostToGuest", VMX_PATH, host_path, guest_path],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        print(f"Failed to copy {host_path} -> {guest_path}: {res.stderr} {res.stdout}")
        sys.exit(1)
    print(f"Copied: {host_path} -> {guest_path}")

if __name__ == "__main__":
    base = Path(r"D:\HK5\CCH_Network")
    copy_to_vm(str(base / "sdn_mpls_demo" / "controller_fabric.py"), "/home/huy/CCH_Network/sdn_mpls_demo/controller_fabric.py")
    copy_to_vm(str(base / "sdn_mpls_demo" / "topology_enterprise_v7.py"), "/home/huy/CCH_Network/sdn_mpls_demo/topology_enterprise_v7.py")
    copy_to_vm(str(base / "sdn_mpls_demo" / "policy.yml"), "/home/huy/CCH_Network/sdn_mpls_demo/policy.yml")
    copy_to_vm(str(base / "sdn_mpls_demo" / "run_live_tests.py"), "/home/huy/CCH_Network/sdn_mpls_demo/run_live_tests.py")
    copy_to_vm(str(base / "scripts" / "test_mpls_failover_runtime.py"), "/home/huy/CCH_Network/scripts/test_mpls_failover_runtime.py")
    copy_to_vm(str(base / "tests" / "test_full_sdn_fabric.py"), "/home/huy/CCH_Network/tests/test_full_sdn_fabric.py")
