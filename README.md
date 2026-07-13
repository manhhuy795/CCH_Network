# CCH Network - Hybrid MPLS L3VPN + SDN Edge Policy

Repository mô phỏng hệ thống mạng Call Center BPO hai site với hai phần:

1. **Network Automation**: source-of-truth YAML, Jinja2, validation, render,
   Ansible workflow, backup/deploy/rollback.
2. **SDN runtime demo**: 110 user trong Mininet, Open vSwitch, OS-Ken
   Controller, OpenFlow 1.3 và dashboard đo kiểm trực tiếp.

SDN không thay thế MPLS. MPLS L3VPN là WAN transport giữa HQ và Branch; SDN
Controller chỉ điều khiển OVS tại access/core/distribution ở hai đầu mạng.

## Cấu trúc

```text
vars/                 Source-of-truth Network Automation
templates/            Template cấu hình
scripts/              Validate, generate, verify, deploy, backup
generated_configs/    Cấu hình đã render
sdn_demo/             Lab SDN nhỏ tương thích Ubuntu 22.04 (legacy)
sdn_mpls_demo/        Lab OS-Ken + 110 user cho Ubuntu 24.04
dashboard/backend/    FastAPI, WebSocket, Mininet/OVS client
dashboard/frontend/   React + TypeScript
tests/                Acceptance và unit test
docs/                 Tài liệu kiến trúc
```

## IP plan

| Nhóm | VLAN | Subnet | User |
|---|---:|---|---:|
| Dự án A | 20 | 172.16.20.0/24 | 20 |
| Dự án B | 30 | 172.16.30.0/24 | 20 |
| Dự án C | 40 | 172.16.40.0/24 | 20 |
| Phòng IT Support | 70 | 172.16.70.0/24 | 10 |
| Telesale | 50 | 172.16.50.0/24 | 20 |
| BackOffice | 60 | 172.16.60.0/24 | 20 |
| Voice | 90 | 172.16.90.0/24 | Service |

Service Zalo/Call App/Social/Internet dùng `172.16.200.10` đến
`172.16.203.10`.

## Kiểm tra Network Automation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/validate_vars.py
python scripts/generate_configs.py
python scripts/verify_network.py
python scripts/generate_sdn_policies.py
pytest
```

`vars/sdn.yml` và `generate_sdn_policies.py` là lớp sinh intent ở mức
automation. Generic REST intent không được xem là controller OpenFlow thật.

## Ubuntu VM mới - copy/paste từ đầu

Dùng Ubuntu 24.04 LTS. Nếu vừa tạo máy ảo mới, mở Terminal 1 và chạy nguyên
block này:

```bash
cd ~/Downloads

sudo apt update
sudo apt install -y \
  git mininet openvswitch-switch iperf3 \
  python3 python3-venv python3-pip python3-dev \
  build-essential curl jq iproute2 procps util-linux \
  nodejs npm
sudo systemctl enable --now openvswitch-switch

if [ ! -d CCH_Network ]; then
  git clone https://github.com/manhhuy795/CCH_Network.git
fi

cd ~/Downloads/CCH_Network
git pull
chmod +x sdn_mpls_demo/*.sh
./sdn_mpls_demo/setup_ubuntu_24_04.sh
sudo ./sdn_mpls_demo/run_topology.sh
```

Giữ Terminal 1 ở màn hình `mininet>`. Không chạy `run_topology.sh` lần thứ hai
ở terminal khác.

## Terminal 1 - chạy lại SDN runtime demo

Script tự khởi động OS-Ken và chờ cổng `6653` trước khi tạo Mininet. Có thể
chạy thủ công ở hai terminal khi cần xem log controller trực tiếp:

```bash
# Terminal 1
./sdn_mpls_demo/run_controller.sh

# Terminal 2
sudo ./sdn_mpls_demo/run_topology.sh
```

Topology tạo:

- `h20_01` đến `h60_20` và `h70_01` đến `h70_10`: 110 user thật.
- `h90`, `hzalo`, `hcall`, `hsocial`, `hinternet`: 5 service.
- 8 OVS do OS-Ken điều khiển.
- CE, Firewall, MPLS Cloud không chịu sự điều khiển của controller.

Đường liên site bắt buộc:

```text
Branch Distribution → CE Router Branch → MPLS L3VPN Cloud
→ CE Router HQ → HQ Core SDN
```

## Chạy dashboard

Terminal 3:

```bash
cd dashboard/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo -E .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Terminal 4:

```bash
cd dashboard/frontend
npm install
npm run dev -- --host 0.0.0.0
```

Mở `http://<IP-Ubuntu-VM>:5173`.

Dashboard hiển thị 6 nhóm user, gồm phòng IT Support có quyền remote/support
tới các user và service. Dropdown vẫn cho chọn từng user thật. Chức năng:

- Ping thật và mô phỏng packet path.
- Throughput TCP bằng iperf3.
- Jitter/loss bằng iperf3 UDP.
- RTT và packet loss bằng ping.
- MOS/R-factor cho chất lượng Call Center.
- Flow table từ 8 OVS.
- Block/unblock OpenFlow tạm thời.
- Link failure/reroute logic phục vụ demo.

## Cleanup

```bash
./sdn_mpls_demo/cleanup.sh
```

## Tài liệu

- `docs/sdn_design.md`
- `sdn_mpls_demo/README.md`
- `sdn_mpls_demo/docs/sdn_design_vi.md`
- `sdn_mpls_demo/docs/demo_script_vi.md`
- `dashboard/README.md`
