#!/usr/bin/env bash
set -euo pipefail

# Script rieng cho Ubuntu 22.04.
# Chay tu thu muc goc repo CCH_Network:
#   chmod +x sdn_demo/ubuntu22_sdn_demo.sh
#   ./sdn_demo/ubuntu22_sdn_demo.sh

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="python3.12"

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

install_python312_on_ubuntu22() {
  note "Cai Python 3.12 cho Ubuntu 22.04"
  sudo apt update
  sudo apt install -y software-properties-common git python3 python3-pip python3-yaml

  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt update
    sudo apt install -y python3.12 python3.12-venv
  fi

  "${PYTHON_BIN}" --version
}

install_mininet_ovs() {
  note "Cai Mininet va Open vSwitch"
  sudo apt install -y mininet openvswitch-switch
  sudo systemctl enable --now openvswitch-switch
  sudo mn -c >/dev/null 2>&1 || true
}

setup_venv_controller() {
  note "Tao .venv Python 3.12 va cai controller"
  cd "${REPO_ROOT}"

  if [[ ! -d .venv ]]; then
    "${PYTHON_BIN}" -m venv .venv
  fi

  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade "pip<26" wheel "setuptools==75.8.0"
  python -m pip install -r sdn_demo/requirements.txt
  python -m pip install --no-build-isolation --no-use-pep517 "ryu==4.34" PyYAML || true

  if ! command -v osken-manager >/dev/null 2>&1 \
    && ! command -v ryu-manager >/dev/null 2>&1 \
    && ! python -c "import os_ken.cmd.manager" >/dev/null 2>&1 \
    && ! python -c "import ryu.cmd.manager" >/dev/null 2>&1; then
    python -m pip install "os-ken>=4.2.1" || true
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
  install_python312_on_ubuntu22
  install_mininet_ovs
  setup_venv_controller
  show_test_notes
  run_demo
}

main "$@"
