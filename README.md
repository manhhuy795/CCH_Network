# Hybrid MPLS L3VPN + SDN Edge Policy Demo cho Call Center BPO

Dự án gồm hai phần:

- **Network Automation**: dùng YAML, Jinja2, Python và Ansible để sinh, kiểm tra, backup/deploy/rollback cấu hình mạng.
- **SDN runtime demo**: dùng Mininet, Open vSwitch, OS-Ken Controller và OpenFlow 1.3 để demo SDN Edge Policy cho Call Center BPO.

MPLS L3VPN trong module SDN là **MPLS L3VPN Logic Cloud**: mô phỏng logic WAN transport giữa HQ và Branch, không phải MPLS provider-grade hoàn chỉnh. Firewall hiện là Linux router mô phỏng Internet Edge nếu chưa cấu hình nftables/iptables thật.

Phân biệt rõ hai track:

- **Network Automation track**: mô tả kiến trúc doanh nghiệp có CE/MPLS L3VPN ở mức thiết kế và cấu hình mẫu.
- **SDN Mininet track**: mô phỏng logic WAN transport; không triển khai PE/P core, VRF, RD/RT, MP-BGP, LDP hoặc MPLS label forwarding thật.

## Source Of Truth

Topology, VLAN, subnet, gateway, host inventory, service, switch mapping và link nằm tại:

```text
vars/network_model.yml
```

Policy chỉ chứa luật mạng tại:

```text
sdn_mpls_demo/policy.yml
```

Luồng dữ liệu:

```text
vars/network_model.yml
→ validation/test
→ Mininet topology
→ FastAPI backend
→ React dashboard
```

## Mô Hình Mạng

| Nhóm | VLAN | Subnet | Số user |
|---|---:|---|---:|
| Dự án A | 20 | 172.16.20.0/24 | 20 |
| Dự án B | 30 | 172.16.30.0/24 | 20 |
| Dự án C | 40 | 172.16.40.0/24 | 20 |
| IT Support | 70 | 172.16.70.0/24 | 10 |
| Telesale | 50 | 172.16.50.0/24 | 20 |
| BackOffice | 60 | 172.16.60.0/24 | 20 |
| Voice Service | 90 | 172.16.90.10 | service |

Tổng user thật trong Mininet: **110**.

Service mô phỏng:

- `h90`: Voice Service, `172.16.90.10`
- `hzalo`: Zalo Service, `172.16.200.10`
- `hcall`: Call App / CRM, `172.16.201.10`
- `hsocial`: Social Media, `172.16.202.10`
- `hinternet`: General Internet Test Service, `172.16.203.10`

## Kiến Trúc

Đường liên site bắt buộc:

```text
HQ Core SDN
→ CE Router HQ
→ MPLS L3VPN Logic Cloud
→ CE Router Branch
→ Branch Distribution SDN
```

Internet HQ:

```text
HQ Core SDN → Firewall HQ → Internet Zone → Service
```

Internet Branch:

```text
Branch Distribution SDN → Firewall Branch → Internet Zone → Service
```

Controller chỉ điều khiển 8 Open vSwitch:

- `access_hq_a`
- `access_hq_b`
- `access_hq_c`
- `access_hq_it`
- `voice_access`
- `core_hq`
- `access_branch`
- `dist_branch`

Controller không điều khiển CE Router, Firewall hoặc MPLS L3VPN Logic Cloud.

## Policy

- Project A/B/C bị cách ly tại `core_hq`.
- VLAN 50 và VLAN 60 bị cách ly tại `dist_branch`.
- Social Media bị drop tại SDN Edge: HQ drop ở `core_hq`, Branch drop ở `dist_branch`.
- User thường được truy cập Voice, Zalo, Call App và General Internet nếu policy cho phép.
- IT Support có quyền remote/support có kiểm soát theo policy.
- Internet/service bên ngoài không được chủ động ping vào user nội bộ.

Voice Flow Priority là nhận diện và áp dụng flow policy ưu tiên cho luồng voice. Đây chưa phải QoS hoàn chỉnh nếu chưa có DSCP, OVS Queue, HTB hoặc bandwidth guarantee.

## Cài Đặt Ubuntu VM

Ubuntu 24.04 được khuyến nghị cho module `sdn_mpls_demo`.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip mininet openvswitch-switch iperf3 curl
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node -v
git clone https://github.com/manhhuy795/CCH_Network.git
cd CCH_Network
chmod +x sdn_mpls_demo/*.sh scripts/*.sh
./sdn_mpls_demo/setup_ubuntu_24_04.sh
cd dashboard/frontend
npm install
cd ../..
```

## Chạy Nhanh

Terminal 1:

```bash
cd ~/Downloads/CCH_Network
sudo mn -c
sudo ./sdn_mpls_demo/run_topology.sh
```

Terminal 2:

```bash
cd ~/Downloads/CCH_Network
./scripts/start_demo.sh --install
```

Các lần sau, nếu dependency đã có:

```bash
./scripts/start_demo.sh
```

Mở dashboard:

```text
http://localhost:5173
```

Nếu mở từ máy host:

```text
http://<IP_VM>:5173
```

## Chạy Thủ Công

Controller:

```bash
./sdn_mpls_demo/run_controller.sh
```

Topology:

```bash
sudo ./sdn_mpls_demo/run_topology.sh
```

Backend:

```bash
python3 -m uvicorn dashboard.backend.app.main:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd dashboard/frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

## Dashboard

React Dashboard là giao diện chính, gồm 4 tab:

- **Tổng quan**: sơ đồ mạng, trạng thái OS-Ken/Mininet/OVS, số user, số switch, số flow, WebSocket.
- **Đo kiểm mạng**: Ping, Throughput TCP, Jitter UDP, chất lượng thoại, real-time metrics.
- **Chính sách & OpenFlow**: policy đang bật, bảng flow dễ đọc, chặn/gỡ chặn thủ công, chi tiết OpenFlow.
- **Nhật ký hệ thống**: sự kiện thao tác, allow/deny, cảnh báo.

Real-time metrics:

- Throughput Mbps từ delta OpenFlow byte counter.
- Delay từ ping định kỳ.
- Packet Loss từ ping.
- Jitter từ ping/UDP probe trong phép đo chủ động.
- Iperf3 chỉ dùng cho đo throughput chủ động, không chạy liên tục mỗi 1-2 giây.

## Test Trong Mininet

Trong prompt `mininet>`:

```text
testpolicy
isolationflows
h20_01 ping -c 2 h30_01
h20_01 ping -c 2 hcall
h20_01 ping -c 2 hsocial
h50_01 ping -c 2 hcall
h50_01 ping -c 2 hsocial
h70_01 ping -c 2 h20_01
hinternet ping -c 2 h20_01
```

Kỳ vọng:

- `h20_01 → h30_01`: fail tại `core_hq`.
- `h20_01 → hcall`: pass qua `fw_hq`.
- `h20_01 → hsocial`: fail tại `core_hq`.
- `h50_01 → hcall`: pass qua `fw_branch`.
- `h50_01 → hsocial`: fail tại `dist_branch`.
- `h70_01 → h20_01`: pass theo policy IT Support.
- `hinternet → h20_01`: fail inbound từ Internet.

## Health Check Và Cleanup

```bash
./scripts/check_demo_health.sh
./scripts/stop_demo.sh
./sdn_mpls_demo/cleanup.sh
sudo mn -c
```

## Network Automation

Các lệnh offline vẫn giữ nguyên:

```bash
python scripts/validate_vars.py
python scripts/generate_configs.py
python scripts/verify_network.py
python scripts/generate_sdn_policies.py
pytest
```

## Lỗi Thường Gặp

- Không thấy controller port 6653: chạy `./sdn_mpls_demo/run_controller.sh` hoặc `./scripts/start_demo.sh`.
- Không ping được dù policy allow: kiểm tra `sdn_mpls_demo/runtime/controller.log`, `testpolicy`, `isolationflows`.
- Dashboard không kết nối WebSocket: kiểm tra backend port 8000 và URL API trong frontend.
- Không chạy được Mininet: chạy `sudo mn -c` rồi khởi động lại topology.

## Giới Hạn Mô Phỏng

- MPLS Cloud chỉ là WAN transport logic.
- Firewall chỉ mô phỏng Internet Edge nếu chưa có iptables/nftables thật.
- Voice Flow Priority chưa phải QoS hoàn chỉnh.
- Softphone như Cfono/Gphone cần kiểm thử thật thêm SIP registration, call setup, RTP media, one-way audio, NAT/SBC và QoS.
- Lab không mở ping ngang giữa Project/Telesale/BackOffice chỉ vì máy agent có cài softphone.
