# Cài đặt Ubuntu 24.04

## Dependency hệ thống

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip mininet openvswitch-switch iperf3 nftables curl nodejs npm
```

Không thay Python hệ thống và không dùng `sudo pip`.

## Chuẩn bị repository

```bash
git clone https://github.com/manhhuy795/CCH_Network.git
cd CCH_Network
chmod +x scripts/*.sh sdn_mpls_demo/*.sh
sudo ./sdn_mpls_demo/setup_ubuntu_24_04.sh
./scripts/start_demo.sh --install
```

OS-Ken dùng virtualenv riêng tại `sdn_mpls_demo/.venv`; dashboard backend dùng `dashboard/backend/.venv`; frontend cài chính xác theo `package-lock.json`.

## Kiểm tra

```bash
sdn_mpls_demo/.venv/bin/python -m pytest -q tests/test_full_sdn_fabric.py
npm run build --prefix dashboard/frontend
```

Mininet live tests chỉ chạy sau khi controller/topology đã sẵn sàng.
