#!/usr/bin/env bash
set -euo pipefail

# Script rieng cho Ubuntu 22.04.
# Chay tu thu muc goc repo CCH_Network:
#   chmod +x sdn_demo/ubuntu22_sdn_demo.sh
#   ./sdn_demo/ubuntu22_sdn_demo.sh

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="python3"

note() {
  echo
  echo "==> $1"
}

require_repo() {
  cd "${REPO_ROOT}"
  if [[ ! -d sdn_demo || ! -f sdn_demo/run_demo.sh ]]; then
    echo "Loi: hay chay script trong repo CCH_Network co thu muc sdn_demo/."
    exit 1
  fi
}

install_python_on_ubuntu22() {
  note "Cai Python mac dinh Ubuntu 22.04 (Python 3.10), Mininet prerequisites"
  sudo apt update
  sudo apt install -y \
    git \
    python3 \
    python3-pip \
    python3-venv \
    python3-yaml \
    build-essential \
    libffi-dev \
    libssl-dev

  "${PYTHON_BIN}" --version
}

install_mininet_ovs() {
  note "Cai Mininet va Open vSwitch"
  sudo apt install -y mininet openvswitch-switch
  sudo systemctl enable --now openvswitch-switch
  sudo mn -c >/dev/null 2>&1 || true
}

setup_venv_controller() {
  note "Tao .venv Python 3.10 va cai Ryu controller"
  cd "${REPO_ROOT}"

  rm -rf .venv
  "${PYTHON_BIN}" -m venv .venv

  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade "pip<24.1" wheel "setuptools==59.6.0"
  python -m pip install -r sdn_demo/requirements.txt
  python -m pip install "ryu==4.34" PyYAML

  if ! command -v ryu-manager >/dev/null 2>&1 \
    && ! python -c "import ryu.cmd.manager" >/dev/null 2>&1; then
    echo "Loi: chua cai duoc ryu-manager."
    exit 1
  fi
}

show_test_notes() {
  note "Lenh test khi vao Mininet"
  cat <<'EOF'
Khi thay prompt "mininet>", copy/paste:

h20 ping -c 2 h30      # fail
h20 ping -c 2 h90      # pass
h20 ping -c 2 hzalo    # pass
h20 ping -c 2 hcall    # pass
h20 ping -c 2 hsocial  # fail
h50 ping -c 2 h60      # fail/limited
h50 ping -c 2 hcall    # pass
h50 ping -c 2 hsocial  # fail

Xem log controller:
tail -f sdn_demo/controller.log

Don dep:
sudo mn -c
EOF
}

run_demo() {
  note "Chay SDN demo"
  cd "${REPO_ROOT}"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  chmod +x sdn_demo/run_demo.sh
  ./sdn_demo/run_demo.sh
}

main() {
  require_repo
  install_python_on_ubuntu22
  install_mininet_ovs
  setup_venv_controller
  show_test_notes
  run_demo
}

main "$@"
