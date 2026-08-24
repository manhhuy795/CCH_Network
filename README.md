# CCH Network — Enterprise v7 + SDN Runtime Demo

Repository này mô tả và mô phỏng kiến trúc mạng Call Center/BPO gồm **HQ + 1 Branch** theo sơ đồ logic v7.

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
- Các mạng routed khác đi liên site qua IPsec L3 VPN trong thiết kế.
- Mỗi site có local Internet breakout qua firewall HA.
- CRM và PBX/Contact Center là hệ thống đối tác, không nằm trong Server Farm nội bộ.
- Server Farm HQ gồm AD, DNS, DHCP, File, NMS/Monitoring, Backup và NTP phụ trợ.

## Simulation honesty

Mininet/OVS không giả lập đầy đủ thiết bị production. Runtime chủ động ghi rõ các abstraction sau:

- `core_hq` và `dist_branch` là một logical OVS đại diện cho từng cặp collapsed Core/Distribution HA.
- `fw_hq` và `fw_telesale` là một namespace nftables đại diện cho active firewall HA cluster tại mỗi site.
- `ce_hq1`, `ce_hq2`, `ce_branch1`, `ce_branch2` là transparent bridge abstraction cho CE L2 handoff.
- `l2vpn_primary` và `l2vpn_backup` là transparent Ethernet bridge abstraction; không có PE/P, label stack, LDP, RSVP hay provider control plane.
- `ipsec_l3` chỉ mô phỏng **routed tunnel behavior**. Lab không có IKE, ESP, XFRM hay bằng chứng mã hóa IPsec thật.

Vì vậy trong báo cáo không được dùng runtime này để tuyên bố đã chứng minh MPLS provider control plane, cryptographic IPsec, firewall appliance HA hay FHRP/MLAG production behavior.

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

Sơ đồ logic thể hiện khoảng `~70 Agent` cho Dự án 2 tại Branch. Runtime cố ý scale-down để VM demo ổn định:

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

Backup attachment path được giữ `standby/down` trong runtime khi Primary hoạt động để tránh tạo L2 loop. Control agent có thể chuyển sang Backup khi Primary bị fail.

## Routed intersite traffic

Branch IoT VLAN 50 và các mạng routed khác không được kéo Layer 2. Chúng đi qua:

```text
Branch Core-Dist
-> ipsec_l3
-> HQ Core-Dist
```

`ipsec_l3` là abstraction logic. Nó chứng minh route/path behavior, không chứng minh mã hóa IPsec.

## Firewall và Partner services

Internet breakout là local tại từng site.

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

Ubuntu 24.04 được khuyến nghị cho runtime chính.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip mininet openvswitch-switch iperf3 nftables tcpdump curl
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
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

Entry point chính thức hiện là:

```text
sdn_mpls_demo/topology_enterprise_v7.py
```

`topology_hybrid_sdn.py` vẫn được giữ để tái sử dụng helper/control-agent đã ổn định và làm lịch sử migration, nhưng không còn là topology executable chính.

Terminal 2 — dashboard:

```bash
cd ~/Downloads/CCH_Network
./scripts/start_demo.sh
```

Lần đầu nếu chưa có dependency dashboard:

```bash
./scripts/start_demo.sh --install
```

Dashboard:

```text
http://127.0.0.1:5173
```

Backend:

```text
http://127.0.0.1:8000
```

## Preflight v7

`start_demo.sh` chạy `scripts/mininet_dashboard_preflight.py` và lưu evidence tại:

```text
runtime_reports/dashboard_preflight.json
```

Các case tối thiểu:

- VLAN 93 HQ -> Branch: ALLOW.
- VLAN 93 Branch -> HQ: ALLOW.
- Project 1 -> Project 3: DENY.
- Project 1 -> Partner PBX: ALLOW.
- Branch IoT -> HQ Monitoring: ALLOW qua `ipsec_l3` abstraction.
- Guest -> Project 2: DENY.

L2VPN Backup ở trạng thái `down/standby` trong preflight là trạng thái thiết kế bình thường.

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

Các thư mục automation vẫn được giữ:

```text
vars/
templates/
inventories/
playbooks/
scripts/
generated_configs/
```

`templates/cisco_ios/ce_l2vpn_edge.j2` chỉ tạo candidate config ở phía customer attachment circuit. Nó **không tự bịa** cấu hình pseudowire/provider MPLS khi chưa có vendor/carrier contract cụ thể.

## Legacy

Các tài liệu, test hoặc generated config chứa VLAN 20/30/40/50/60/70 hoặc tên Project A/B/C thuộc mô hình trước v7 phải được xem là legacy cho đến khi được cập nhật/xóa khỏi nhánh migration.

Source of truth v7 mới là chuẩn để phát triển tiếp.
