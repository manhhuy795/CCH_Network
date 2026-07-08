#!/usr/bin/env bash
set -euo pipefail

# Live SDN web dashboard for the Mininet/OVS lab.
# Run after ./sdn_demo/run_demo.sh is already running in another terminal.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${SCRIPT_DIR}/backend"

cd "${BACKEND_DIR}"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

cat <<'EOF'

============================================================
SDN Live Dashboard
============================================================
Mo trinh duyet:

  http://127.0.0.1:8000

Neu truy cap tu Windows host vao Ubuntu VM, dung IP cua VM:

  http://<ubuntu-vm-ip>:8000

Luu y: nen chay ./sdn_demo/run_demo.sh truoc o terminal khac.
============================================================

EOF

sudo -E "${BACKEND_DIR}/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
