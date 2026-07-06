#!/usr/bin/env bash
set -euo pipefail

# Script cai dat va chay SDN demo tren Ubuntu VM.
# Chay tu thu muc goc repo:
#   chmod +x sdn_demo/setup_ubuntu_vm_vi.sh
#   ./sdn_demo/setup_ubuntu_vm_vi.sh
# Neu muon cai xong chay demo luon:
#   ./sdn_demo/setup_ubuntu_vm_vi.sh --run

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_AFTER_SETUP="false"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"

if [[ "${1:-}" == "--run" ]]; then
  RUN_AFTER_SETUP="true"
fi

print_step() {
  echo
  echo "================================================================"
  echo "$1"
  echo "================================================================"
}

require_ubuntu_like() {
  if [[ ! -f /etc/os-release ]]; then
    echo "Khong tim thay /etc/os-release. Script nay duoc viet cho Ubuntu/Debian."
    exit 1
  fi

  # shellcheck disable=SC1091
  source /etc/os-release
  case "${ID_LIKE:-$ID}" in
    *debian*|*ubuntu*)
      ;;
    *)
      echo "Canh bao: he dieu hanh khong phai Ubuntu/Debian. Script van thu chay tiep."
      ;;
  esac
}

install_system_packages() {
  print_step "1. Cai goi he thong: Python 3.12, Mininet, Open vSwitch"
  sudo apt update
  sudo apt install -y \
    git \
    python3.12 \
    python3.12-venv \
    python3-pip \
    python3-yaml \
    mininet \
    openvswitch-switch

  sudo systemctl enable --now openvswitch-switch

  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Loi: khong tim thay ${PYTHON_BIN} sau khi cai dat."
    echo "Khuyen nghi dung Ubuntu 24.04 LTS vi co san Python 3.12 trong apt."
    echo "Neu ban dung Python khac, co the chay: PYTHON_BIN=python3 ./sdn_demo/setup_ubuntu_vm_vi.sh"
    exit 1
  fi
}

setup_python_env() {
  print_step "2. Tao Python virtualenv va cai OS-Ken/Ryu"
  cd "${REPO_ROOT}"

  if [[ ! -d .venv ]]; then
    "${PYTHON_BIN}" -m venv .venv
  fi

  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade pip

  if python -m pip install -r sdn_demo/requirements.txt; then
    echo "Da cai OS-Ken thanh cong bang pip."
  else
    echo "Cai OS-Ken bang pip bi loi, thu cai Ryu thay the."
    python -m pip install ryu PyYAML || true
  fi

  if command -v osken-manager >/dev/null 2>&1 || command -v ryu-manager >/dev/null 2>&1; then
    return
  fi

  if python -c "import os_ken" >/dev/null 2>&1 || python -c "import ryu" >/dev/null 2>&1; then
    echo "Da cai module controller, co the chay bang python -m neu entrypoint khong co."
    return
  fi

  echo "Pip chua cai duoc OS-Ken/Ryu. Thu fallback bang apt neu Ubuntu co goi python3-ryu."
  if apt-cache show python3-ryu >/dev/null 2>&1; then
    sudo apt install -y python3-ryu
  else
    echo "Khong thay goi apt python3-ryu tren ban Ubuntu nay."
  fi
}

verify_tools() {
  print_step "3. Kiem tra cong cu"
  cd "${REPO_ROOT}"
  # shellcheck disable=SC1091
  source .venv/bin/activate

  echo "Python:"
  python --version

  echo
  echo "Mininet:"
  mn --version || true

  echo
  echo "Open vSwitch:"
  ovs-vsctl --version | head -n 1 || true

  echo
  if command -v osken-manager >/dev/null 2>&1; then
    echo "Controller: osken-manager da san sang"
  elif command -v ryu-manager >/dev/null 2>&1; then
    echo "Controller: ryu-manager da san sang"
  elif python -c "import os_ken" >/dev/null 2>&1; then
    echo "Controller: module os_ken da san sang, run_demo.sh se chay bang python -m os_ken.cmd.manager"
  elif python -c "import ryu" >/dev/null 2>&1; then
    echo "Controller: module ryu da san sang, run_demo.sh se chay bang python -m ryu.cmd.manager"
  else
    echo "Loi: chua tim thay OS-Ken/Ryu."
    echo "Neu VM dang dung Python qua moi, vi du Python 3.14, hay thu:"
    echo "  source .venv/bin/activate"
    echo "  pip install 'setuptools<81' eventlet PyYAML"
    echo "  pip install ryu"
    echo "Khuyen nghi dung Ubuntu 24.04 LTS voi Python 3.12 de tuong thich on dinh hon."
    exit 1
  fi
}

show_next_steps() {
  print_step "4. Huong dan chay demo"
  cat <<'EOF'
Neu chua chay demo, dung lenh:

  source .venv/bin/activate
  ./sdn_demo/run_demo.sh

Khi thay prompt:

  mininet>

Hay copy/paste cac lenh test:

  h20 ping -c 2 h30      # mong doi fail
  h20 ping -c 2 h90      # mong doi pass
  h20 ping -c 2 hzalo    # mong doi pass
  h20 ping -c 2 hcall    # mong doi pass
  h20 ping -c 2 hsocial  # mong doi fail
  h50 ping -c 2 h60      # mong doi fail/limited
  h50 ping -c 2 hcall    # mong doi pass
  h50 ping -c 2 hsocial  # mong doi fail

Xem log controller o terminal khac:

  tail -f sdn_demo/controller.log

Don dep Mininet khi can:

  sudo mn -c
EOF
}

main() {
  require_ubuntu_like
  install_system_packages
  setup_python_env
  chmod +x "${SCRIPT_DIR}/run_demo.sh"
  verify_tools
  show_next_steps

  if [[ "${RUN_AFTER_SETUP}" == "true" ]]; then
    print_step "5. Chay SDN demo Mininet"
    cd "${REPO_ROOT}"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    ./sdn_demo/run_demo.sh
  fi
}

main "$@"
