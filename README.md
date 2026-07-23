# Hybrid MPLS L3VPN + SDN Edge Policy Demo cho Call Center BPO

> **Demo chinh thuc dung cho bao ve:** `sdn_mpls_demo/`.
> `sdn_demo/` la demo legacy, khong dung trong buoi bao ve chinh de tranh nham entry point.

## Xác Thực Và Phân Quyền Phase 49

Dashboard dùng xác thực người dùng bằng session cookie phía server và CSRF token. Operator token là credential máy dành riêng cho runtime script/API; token không được đưa vào frontend, không hiển thị trên dashboard và không ghi vào report.

| Vai trò | Quyền chính |
|---|---|
| `admin` | Quản lý user/role, xem audit, dashboard và runtime |
| `operator` | Dashboard, ping/iperf/voice quality, link/policy runtime và activity |
| `viewer` | Chỉ xem dashboard/topology/trạng thái |
| `auditor` | Xem dashboard và audit event |

Không có mật khẩu mặc định trong repository. Tạo admin lần đầu bằng cách nhập mật khẩu qua stdin, không đặt mật khẩu trên command line:

```bash
cd ~/Downloads/CCH_Network
read -r -s ADMIN_PASSWORD; echo
printf '%s\n' "$ADMIN_PASSWORD" | .venv/bin/python scripts/phase49_bootstrap_admin.py --username admin --password-stdin
unset ADMIN_PASSWORD
```


## Simulation Honesty

- `fw_hq` va `fw_telesale` trong SDN/Mininet demo la **stateful nftables firewall** chay trong hai Linux network namespace rieng.
- Hai firewall thuc thi Internet service policy, inbound default-deny, conntrack return traffic va counter that; chung van la lab, khong thay the firewall production.
- MPLS trong demo la **MPLS L3VPN Logic Cloud**, khong phai PE/P provider core hoan chinh.

Dự án gồm hai phần:

- **Network Automation**: dùng YAML, Jinja2, Python và Ansible để sinh, kiểm tra, backup/deploy/rollback cấu hình mạng.
- **SDN runtime demo**: dùng Mininet, Open vSwitch, OS-Ken Controller và OpenFlow 1.3 để demo SDN Edge Policy cho Call Center BPO.

MPLS L3VPN trong module SDN là **MPLS L3VPN Logic Cloud**: mô phỏng logic WAN transport giữa HQ và Branch, không phải MPLS provider-grade hoàn chỉnh. Internet breakout được kiểm soát thật bằng nftables tại `fw_hq` và `fw_telesale`.

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
| PBX/SBC Voice Service | 90 | 172.16.90.10 | service |

Tổng user thật trong Mininet: **110**.

Service mô phỏng:

- `h90`: PBX/SBC Voice Service, `172.16.90.10`
- `hzalo`: Zalo Service, `172.16.200.10`
- `hcall`: Call App / CRM, `172.16.201.10`
- `hsocial`: Social Media, `172.16.202.10`
- `hinternet`: General Internet Test Service, `172.16.203.10`

## VLAN Tagging

Phase 4 deferred as optional enterprise fidelity enhancement.

VLAN được biểu diễn bằng subnet và phân tách Access Switch trong phiên bản hiện tại; dot1q tagging thật là phần mở rộng. Policy enforcement hiện dựa trên IP subnet tại SDN Edge/Core/Distribution nên không phụ thuộc dot1q tagging để chứng minh segmentation trong lab.

## Kiến Trúc

Đường liên site bắt buộc:

```text
HQ Core SDN
→ CE Router HQ
→ MPLS L3VPN Logic Cloud
→ CE Router Telesale
→ Telesale Distribution SDN
```

Internet HQ:

```text
HQ Core SDN → Firewall HQ → Internet Zone → Service
```

Internet Branch:

```text
Telesale Distribution SDN → Firewall Telesale → Internet Zone → Service
```

Controller chỉ điều khiển 12 Open vSwitch:

- `access_hq_a`
- `access_hq_b`
- `access_hq_c`
- `access_hq_it`
- `voice_access`
- `core_hq`
- `access_telesale`
- `dist_telesale`
- `access_backoffice` (logical ID; Linux runtime bridge: `access_bo`)
- `access_iot`
- `access_guest`
- `infra_access`

Controller không điều khiển CE Router, Firewall hoặc MPLS L3VPN Logic Cloud.

## Policy

- Project A/B/C bị cách ly tại `core_hq`.
- Telesale VLAN 50 → BackOffice VLAN 60 bị chặn tại `dist_telesale`.
- BackOffice VLAN 60 → Telesale VLAN 50 bị chặn tại `core_hq`.
- Social Media bị drop tại SDN Edge: HQ drop ở `core_hq`, Telesale drop ở `dist_telesale`.
- User thường được truy cập Voice, Zalo, Call App và General Internet nếu policy cho phép.
- IT Support có quyền remote/support có kiểm soát theo policy.
- Internet/service bên ngoài không được chủ động ping vào user nội bộ.

Voice Flow Priority là nhận diện và áp dụng flow policy ưu tiên cho luồng voice. Đây chưa phải QoS hoàn chỉnh nếu chưa có DSCP, OVS Queue, HTB hoặc bandwidth guarantee.

## Cài Đặt Ubuntu VM

Ubuntu 24.04 được khuyến nghị cho module `sdn_mpls_demo`.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip mininet openvswitch-switch iperf3 nftables tcpdump curl
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

`start_demo.sh` chỉ tạo/đọc operator token cho các script runtime và lưu token trong `logs/operator.token`; giá trị token không được in ra. Người dùng truy cập dashboard bằng tài khoản Phase 49, không dán operator token vào giao diện.

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

React Dashboard là giao diện chính cho IT Support và Network Administrator:

- **Tổng quan**: trạng thái từng thành phần, số user/host, cảnh báo và quick action.
- **Topology**: sơ đồ HQ, MPLS logic, Telesale, BackOffice và Internet/Services; packet path lấy từ backend runtime.
- **Kiểm tra kết nối**: Ping thật, TCP throughput, UDP jitter và Voice Quality.
- **Chính sách & OpenFlow**: policy, enforcement point, cookie, priority, match/action và flow runtime.
- **Hiệu năng**: metrics, session iperf và kết quả đo có session ID.
- **Sự kiện & nhật ký**: activity event, audit event, allow/deny, lỗi và request ID.

Navigation và thao tác được giới hạn theo role. `viewer` không thấy thao tác runtime; `auditor` chỉ xem audit; `admin` mới quản lý user/role. Dashboard không hiển thị token máy.

Real-time metrics:

- Throughput Mbps từ delta OpenFlow byte counter.
- Delay từ ping định kỳ.
- Packet Loss từ ping.
- Jitter từ ping/UDP probe trong phép đo chủ động.
- Iperf3 chỉ dùng cho đo throughput chủ động, không chạy liên tục mỗi 1-2 giây.

## Kiểm Thử Runtime Chi Tiết Phase 49

Sau khi topology, backend và frontend đang chạy, dùng script dưới đây để kiểm tra toàn bộ status và event bằng dữ liệu thật:

```bash
cd ~/Downloads/CCH_Network
.venv/bin/python scripts/phase49_detailed_status_event_test.py
```

Script kiểm tra:

- port controller/backend/frontend, Mininet Control Agent, Open vSwitch và OpenFlow flow tại `core_hq`;
- toàn bộ component trong `/api/health` và `/api/live/status`;
- unauthenticated `401`, RBAC `403`, operator token không có quyền admin;
- login đúng/sai, `/api/auth/me`, refresh, logout và session hết hiệu lực;
- tạo user `admin/operator/viewer/auditor`, disable/reenable và đổi role;
- ping thật ALLOW, ping thật POLICY DENIED và quyền runtime của từng role;
- activity event, audit event, request history và kiểm tra report không chứa token/mật khẩu.

Kết quả được lưu tại `runtime_reports/phase49_detailed_status_events_<timestamp>/summary.json` và `runtime.log`. Script không ghi operator token hoặc mật khẩu test vào console hay artifact.

Gate regression đầy đủ:

```bash
./scripts/phase49_auth_rbac_gate.sh full --reuse-running
sudo -n -E bash scripts/phase44_45_combined_acceptance.sh
```

Chỉ kết luận PASS khi command trả exit code `0` và artifact có đầy đủ case PASS.


## Ranh Gioi Network Automation Va SDN Runtime

Du an co hai track rieng, khong tron lan:

- **Network Automation**: dung `vars/`, `templates/`, `inventories/`, `playbooks/`, `scripts/`, `generated_configs/` va `tests/` de quan ly YAML, validation, Jinja2, Ansible, generated Cisco/firewall config, backup/deploy/verify.
- **SDN runtime**: dung `sdn_mpls_demo/` de chay Mininet, Open vSwitch, OS-Ken va OpenFlow 1.3 cho demo runtime.
- **Source of truth chung**: ca hai track cung tham chieu `vars/network_model.yml` de giu nhat quan ve vai tro node, link logic, switch, firewall, CE va MPLS logic cloud.

Luu y quan trong: generated Cisco config khong duoc load vao OVS va khong dung de dung Mininet. Mininet topology duoc tao bang Python trong `sdn_mpls_demo/topology_hybrid_sdn.py`; Cisco/firewall config la artifact automation de review, lab, backup/deploy tren thiet bi that hoac emulator phu hop.

## Test Trong Mininet

Checkpoint nftables Phase 44: `docs/phase_44_ubuntu_firewall_validation_vi.md`.

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
- `h20_01 → hsocial`: fail tại `fw_hq` bằng nftables.
- `h50_01 → hcall`: pass qua `fw_telesale`.
- `h50_01 → hsocial`: fail tại `fw_telesale` bằng nftables.
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
- Social/Internet inbound bị chặn tại `fw_hq` hoặc `fw_telesale`; Project và cross-site isolation vẫn bị chặn bằng OpenFlow.
- Firewall dùng nftables/conntrack thật trong namespace Mininet, nhưng vẫn là firewall lab chứ không phải appliance production.
- Voice Flow Priority chưa phải QoS hoàn chỉnh.
- Softphone như Cfono/Gphone cần kiểm thử thật thêm SIP registration, call setup, RTP media, one-way audio, NAT/SBC và QoS.
- Lab không mở ping ngang giữa Project/Telesale/BackOffice chỉ vì máy agent có cài softphone.


## Phase 46: Automation, Documentation Va Ubuntu Gate

Phase 46 gom mot gate cho automation, tai lieu va runtime Ubuntu. Gate khong tu coi port dang listen la healthy, khong coi socket stale la agent online, khong ghi token vao artifact va khong tu khoi dong topology khi chua co tuy chon ro rang.

~~~bash
bash scripts/phase46_automation_docs_gate.sh preflight --reuse-running
bash scripts/phase46_automation_docs_gate.sh static --reuse-running
bash scripts/phase46_automation_docs_gate.sh automation --reuse-running
bash scripts/phase46_automation_docs_gate.sh docs --reuse-running
sudo -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 bash scripts/phase46_automation_docs_gate.sh runtime --reuse-running
~~~

Report tao tai runtime_reports/phase46_automation_docs_<UTC>/; xem summary.json va NEXT_ACTION.md neu FAIL/BLOCKED. Tai lieu chi tiet nam trong docs/architecture.md, docs/installation_ubuntu.md, docs/runtime_operations.md, docs/troubleshooting.md, docs/testing_and_acceptance.md va docs/security_notes.md.

## Enterprise VLAN Zones

Enterprise extension dùng các VLAN chưa có trong mô hình cũ để tránh xung đột với VLAN 10 Management:

| VLAN | Zone | Subnet | Chính sách chính |
|---:|---|---|---|
| 80 | Guest | 172.16.80.0/24 | DHCP/DNS/NTP và General Internet; chặn mạng nội bộ |
| 100 | Infrastructure Services | 172.16.100.0/24 | DHCP, DNS, NTP, Monitoring |
| 110 | IoT/UPS | 172.16.110.0/24 | Chỉ hạ tầng cần thiết; IT Support quản trị theo least privilege |

VLAN 10 vẫn dành cho Management. Mô hình runtime có 110 user doanh nghiệp, 5 service hiện hữu, 9 endpoint Guest/IoT/UPS, 4 infrastructure service và 12 OVS. Chi tiết xem `docs/enterprise_vlan_plan_vi.md`.
