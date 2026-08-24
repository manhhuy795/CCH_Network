# CCH Network — Enterprise v7 + SDN Runtime Demo

Repository mô tả và mô phỏng kiến trúc mạng Call Center/BPO gồm **HQ + 1 Branch** theo sơ đồ logic v7.

Sơ đồ chuẩn:

- `docs/assets/enterprise_logical_topology_v7.svg`

Tài liệu topology chi tiết:

- `docs/topology.md`

## Kiến trúc v7

Thiết kế mục tiêu dùng **2-tier Collapsed Core / Distribution** tại cả HQ và Branch.

Các điểm bắt buộc:

- Dự án 1: VLAN 101.
- Dự án 2: VLAN 93, dùng chung giữa HQ và Branch.
- Dự án 3: VLAN 103.
- Dự án 4: VLAN 104.
- VLAN 93 dùng subnet `10.10.93.0/24`.
- Gateway VLAN 93 là `10.10.93.1` và **chỉ nằm tại HQ**.
- Branch **không có SVI/gateway VLAN 93**.
- VLAN 93 là VLAN duy nhất được mở rộng Layer 2 giữa hai site.
- MPLS L2VPN có Primary và Backup; CE1 ưu tiên Primary, CE2 dùng Backup.
- Các mạng routed khác đi liên site qua IPsec L3 VPN giữa hai Firewall HA trong thiết kế.
- Mỗi site có local Internet breakout và hai circuit ISP riêng theo vai trò Primary/Backup.
- CRM và PBX/Contact Center là hệ thống đối tác, không nằm trong Server Farm nội bộ.
- Server Farm HQ gồm AD, DNS, DHCP, File, NMS/Monitoring, Backup và NTP phụ trợ.

## Simulation honesty

Mininet/OVS không giả lập đầy đủ thiết bị production. Runtime chủ động ghi rõ các abstraction sau:

- `core_hq` và `dist_branch` là logical OVS đại diện cho từng cặp collapsed Core/Distribution HA.
- `fw_hq` và `fw_telesale` là namespace nftables đại diện cho active firewall HA cluster tại mỗi site.
- `ce_hq1`, `ce_hq2`, `ce_branch1`, `ce_branch2` là transparent bridge abstraction cho CE L2 handoff.
- `l2vpn_primary` và `l2vpn_backup` là transparent Ethernet bridge abstraction; không có PE/P, label stack, LDP, RSVP hay provider control plane.
- `ipsec_l3` mô phỏng **routed tunnel behavior giữa `fw_hq` và `fw_telesale`**. Lab không có IKE, ESP, XFRM hay bằng chứng mã hóa IPsec thật.

Vì vậy không dùng runtime này để tuyên bố đã chứng minh MPLS provider control plane, cryptographic IPsec, firewall appliance HA hay FHRP/MLAG production behavior.

## Source of truth

Các file chính:

```text
vars/network_model.yml
vars/vlans.yml
vars/sites.yml
vars/routing.yml
vars/firewall_policies.yml
vars/acl_policies.yml
vars/interface_mapping.yml
vars/sdn.yml
sdn_mpls_demo/policy.yml
```

Luồng dữ liệu:

```text
Source of truth
-> validation / policy engine
-> Mininet + Open vSwitch + OS-Ken
-> FastAPI backend
-> React dashboard
```

## Runtime scale

Sơ đồ logic thể hiện khoảng `~70 Agent` cho Dự án 2 tại Branch. Runtime scale-down để VM demo ổn định:

| Nhóm | VLAN | Runtime user | Vị trí |
|---|---:|---:|---|
| Dự án 1 | 101 | 20 | HQ |
| Dự án 2 | 93 | 20 | 10 HQ + 10 Branch |
| Dự án 3 | 103 | 20 | HQ |
| Dự án 4 | 104 | 20 | HQ |
| IT Support | 110 | 10 | HQ |

Tổng corporate user runtime: **90**.

Ngoài ra lab có Guest, IoT/UPS, 7 infrastructure service và 5 external/partner service simulator.

## VLAN 93 L2VPN

Primary path:

```text
Project 2 Branch
-> Branch Access
-> CORE-DIST Branch
-> CE-BR1
-> MPLS L2VPN Primary
-> CE-HQ1
-> CORE-DIST HQ
-> gateway 10.10.93.1
```

Backup path:

```text
CORE-DIST Branch
-> CE-BR2
-> MPLS L2VPN Backup
-> CE-HQ2
-> CORE-DIST HQ
```

Backup attachment path được giữ `standby/down` khi Primary hoạt động để tránh L2 loop. Control agent chuyển sang Backup khi Primary được fail qua runtime control.

## Routed intersite traffic

Branch IoT VLAN 50 và các mạng routed khác không được kéo Layer 2. Chúng đi theo:

```text
Branch Core-Dist
-> Firewall Branch
-> ipsec_l3
-> Firewall HQ
-> HQ Core-Dist
```

Theo chiều ngược lại, HQ routed network dùng cùng firewall-to-firewall overlay. `ipsec_l3` chỉ chứng minh route/path behavior, không chứng minh mã hóa IPsec. VLAN 93 không đi qua path này.

## DHCP tập trung

DHCP Server là `10.10.100.10` tại HQ. Candidate config sinh relay từ `vars/routing.yml`:

- HQ: VLAN 93, 101, 103, 104, 110, 120, 140.
- Branch: VLAN 50.
- Branch không có SVI VLAN 93 nên không sinh helper cho VLAN 93 tại Branch; DHCP broadcast VLAN 93 đi qua L2VPN tới HQ.

## Security policy

- Project VLANs bị cách ly lẫn nhau.
- Project chỉ được truy cập DHCP, DNS, AD, File và NTP trong Server VLAN 100; NMS/Backup không mở mặc định.
- Guest chỉ được DHCP/DNS/NTP và General Internet, không được lateral vào internal network.
- HQ IoT chỉ được DHCP/DNS/NTP/NMS và không có broad Internet allow.
- Branch IoT chỉ được các infrastructure service đã khai báo qua firewall-to-firewall routed overlay.
- Candidate config không tự tạo Port-channel, StackWise, VSS, MLAG hay multi-chassis behavior khi platform/physical cabling chưa được xác nhận.

## Firewall và Partner services

Internet breakout là local tại từng site. HQ và Branch có circuit Internet riêng; các object `primary`/`backup` trong routing automation là **role**, không phải circuit vật lý dùng chung.

Project 2 Branch là ngoại lệ về hướng gateway: vì VLAN 93 có gateway tại HQ, traffic Internet/Partner của Project 2 Branch đi L2 về HQ rồi mới qua `fw_hq`.

Partner services:

- `h90`: Partner PBX / Contact Center.
- `hcall`: Partner CRM.

Internet/service simulators:

- `hzalo`: Internet App simulator.
- `hsocial`: Social Media simulator.
- `hinternet`: General Internet test service.

## SDN boundary

OS-Ken chỉ điều khiển 6 OVS:

```text
access_floor1
access_floor2
core_hq
access_branch
dist_branch
infra_access
```

CE bridges, L2VPN bridges, firewall namespaces, `ipsec_l3` và Internet/Partner service zone không phải OpenFlow target.

## Cài đặt Ubuntu

Ubuntu 24.04 được khuyến nghị cho runtime chính. Script setup cài cả `python3-yaml` vì topology chạy bằng system Python của Mininet.

```bash
chmod +x sdn_mpls_demo/*.sh scripts/*.sh
./sdn_mpls_demo/setup_ubuntu_24_04.sh
cd dashboard/frontend
npm install
cd ../..
```

## Chạy chương trình

Terminal 1 — topology:

```bash
cd ~/Downloads/CCH_Network
sudo mn -c
sudo ./sdn_mpls_demo/run_topology.sh
```

Entry point chính thức:

```text
sdn_mpls_demo/topology_enterprise_v7.py
```

`topology_hybrid_sdn.py` chỉ được giữ để tái sử dụng helper/control-agent đã ổn định; không còn là topology executable chính.

Terminal 2 — dashboard:

```bash
cd ~/Downloads/CCH_Network
./scripts/start_demo.sh
```

Lần đầu nếu chưa có dependency dashboard:

```bash
./scripts/start_demo.sh --install
```

Dashboard: `http://127.0.0.1:5173`

Backend: `http://127.0.0.1:8000`

## Merge / regression gate

Static gate dùng toàn bộ active pytest suite; không có pytest filter để che test topology cũ.

```bash
./scripts/phase47_full_regression_gate.sh static
./scripts/phase47_full_regression_gate.sh frontend
```

Frontend gate chạy `lint`, `test`, `typecheck` và `build`.

Sau khi topology và dashboard đang chạy:

```bash
./scripts/phase47_full_regression_gate.sh runtime
```

Hoặc chạy toàn bộ:

```bash
./scripts/phase47_full_regression_gate.sh full
```

## Preflight v7

`start_demo.sh` chạy `scripts/mininet_dashboard_preflight.py` và lưu evidence tại `runtime_reports/dashboard_preflight.json`.

Các case tối thiểu:

- VLAN 93 HQ -> Branch: ALLOW.
- VLAN 93 Branch -> HQ: ALLOW.
- Project 1 -> Project 3: DENY.
- Project 1 -> Partner PBX: ALLOW.
- Branch IoT -> HQ Monitoring: ALLOW qua `fw_telesale -> ipsec_l3 -> fw_hq`.
- Guest -> Project 2: DENY.

L2VPN Backup `down/standby` là trạng thái thiết kế bình thường.

## Xác thực dashboard

Dashboard dùng session cookie phía server, CSRF và RBAC. Không có mật khẩu mặc định hard-code trong repository.

Tạo admin lần đầu:

```bash
cd ~/Downloads/CCH_Network
read -r -s ADMIN_PASSWORD; echo
printf '%s\n' "$ADMIN_PASSWORD" | ./scripts/phase49_bootstrap_admin.py --username admin --password-stdin
unset ADMIN_PASSWORD
```

Các role hiện có:

| Role | Quyền chính |
|---|---|
| `admin` | Quản lý user/role, dashboard, runtime, audit |
| `operator` | Dashboard và thao tác runtime được cho phép |
| `viewer` | Chỉ xem |
| `auditor` | Xem audit |

## Network Automation

Các thư mục automation:

```text
vars/
templates/
inventories/
playbooks/
scripts/
generated_configs/
```

`templates/cisco_ios/ce_l2vpn_edge.j2` chỉ tạo candidate config phía customer attachment circuit. Nó **không tự bịa** pseudowire/provider MPLS khi chưa có vendor/carrier contract cụ thể.

`generated_configs/` không lưu candidate config cũ; hãy regenerate từ source of truth v7 trước khi kiểm tra hoặc triển khai.
