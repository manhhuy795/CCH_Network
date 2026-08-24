# Topology v7

Sơ đồ logic chuẩn dùng cho báo cáo và đối chiếu kiến trúc:

- `docs/assets/enterprise_logical_topology_v7.svg`

Source of truth dùng cho runtime và automation:

- `vars/network_model.yml`
- `vars/vlans.yml`
- `vars/routing.yml`
- `vars/firewall_policies.yml`
- `vars/interface_mapping.yml`
- `sdn_mpls_demo/policy.yml`

## Kiến trúc chính

Hệ thống chỉ có **HQ + 1 Branch**. Cả hai site dùng mô hình **2-tier Collapsed Core / Distribution**.

HQ có:

- Dự án 1: VLAN 101, `10.10.101.0/24`.
- Dự án 2: VLAN 93, `10.10.93.0/24`.
- Dự án 3: VLAN 103, `10.10.103.0/24`.
- Dự án 4: VLAN 104, `10.10.104.0/24`.
- Server/Infrastructure: VLAN 100, gồm AD, DNS, DHCP, File, NMS/Monitoring, Backup và NTP phụ trợ.
- Office/IT Support, Guest và HQ IoT dùng VLAN riêng trong lab; các VLAN này là implementation choice của demo khi sơ đồ logic không chốt số VLAN cụ thể.

Branch có:

- Dự án 2 trên VLAN 93.
- IoT trên VLAN 50.
- Không có SVI/gateway VLAN 93 tại Branch.

## VLAN 93 — MPLS L2VPN

VLAN 93 là VLAN duy nhất được kéo Layer 2 giữa HQ và Branch.

- Subnet: `10.10.93.0/24`.
- Gateway: `10.10.93.1` tại HQ.
- Branch không tạo gateway VLAN 93.
- Primary path: `CORE-DIST-HQ -> CE-HQ1 -> MPLS L2VPN Primary -> CE-BR1 -> CORE-DIST-BR`.
- Backup path: `CORE-DIST-HQ -> CE-HQ2 -> MPLS L2VPN Backup -> CE-BR2 -> CORE-DIST-BR`.

Trong Mininet, CE và MPLS L2VPN là transparent Linux bridge. Backup attachment path ở **standby/down** khi Primary hoạt động để tránh Layer-2 loop. Khi Primary bị fail qua control agent, runtime chuyển sang Backup.

Lab **không** mô phỏng PE/P router, MPLS label stack, LDP/RSVP hoặc provider control plane. Kết quả chỉ chứng minh Ethernet service behavior của VPWS/E-Line logic.

## IPsec L3 giữa HQ và Branch

Các mạng routed không phải VLAN 93 đi liên site theo kiến trúc:

```text
CORE-DIST-HQ -> Firewall HQ -> IPsec L3 overlay qua Internet -> Firewall Branch -> CORE-DIST-BR
```

Runtime dùng `ipsec_l3` như một Linux router để mô phỏng **routed tunnel behavior giữa hai firewall namespaces**:

```text
fw_hq -> ipsec_l3 -> fw_telesale
```

- HQ/Branch gateway gửi traffic liên site tới firewall local.
- Firewall local route các prefix remote vào `ipsec_l3` abstraction.
- Firewall phía xa nhận traffic tunnel rồi chuyển vào LAN local.
- VLAN 93 không được route qua IPsec.

Runtime **không** triển khai IKE, ESP, XFRM hay mã hóa IPsec thật. Dashboard/tài liệu chỉ được ghi là `IPsec L3 abstraction` hoặc `routed tunnel abstraction`, không dùng nó làm bằng chứng cryptographic IPsec.

## DHCP tập trung

DHCP Server là `10.10.100.10` tại HQ. `vars/routing.yml` là source of truth cho DHCP relay.

- HQ relay trên SVI: VLAN 93, 101, 103, 104, 110, 120, 140.
- Branch relay trên SVI VLAN 50.
- Branch không có SVI VLAN 93 nên không tạo `ip helper-address` cho VLAN 93 tại Branch; DHCP của VLAN 93 đi qua broadcast domain L2VPN tới HQ.

Candidate Cisco config sinh `ip helper-address 10.10.100.10` từ source of truth này.

## Firewall và Internet breakout

Mỗi site có firewall HA trong thiết kế. Mininet không dựng hai appliance firewall độc lập cho mỗi site; thay vào đó:

- `fw_hq` là namespace nftables đại diện cho active firewall HA cluster tại HQ.
- `fw_telesale` là runtime compatibility name của firewall HA Branch.
- Mỗi firewall có inside, outside và logical tunnel attachment.

Internet breakout là local tại từng site. HQ và Branch có hai circuit ISP riêng; các đối tượng Primary/Backup dùng trong automation chỉ là role, không phải một circuit vật lý dùng chung.

VLAN 93 dùng gateway tại HQ nên Internet/Partner traffic của Project 2 Branch đi L2VPN về HQ trước khi qua firewall HQ.

## Partner CRM/PBX

CRM và PBX/Contact Center nằm ngoài Server Farm nội bộ.

- `h90`: Partner PBX / Contact Center.
- `hcall`: Partner CRM.

Hai service nằm sau `internet_zone`/Partner Service Zone trong lab và được kiểm soát như external/partner services.

## Security segmentation

- Project 1/2/3/4 bị cách ly lẫn nhau.
- Project chỉ được truy cập DHCP, DNS, AD, File và NTP trong Server VLAN 100; NMS/Monitoring và Backup không được mở mặc định.
- Guest chỉ được bootstrap services cần thiết và General Internet, không được lateral vào mạng nội bộ.
- HQ IoT chỉ được DHCP/DNS/NTP/NMS và không có broad Internet allow.
- Branch IoT chỉ được các service hạ tầng đã khai báo và đi HQ qua firewall-to-firewall `ipsec_l3` abstraction.

## Physical redundancy boundary

Candidate config **không** tự tạo Port-channel, StackWise, VSS, MLAG hay multi-chassis EtherChannel vì platform/physical cabling chưa được chốt. Các uplink trong automation là logical single-interface placeholders; physical diagram/config cuối phải được xác nhận theo thiết bị thật.

## Runtime scale

Sơ đồ logic ghi khoảng `~70 Agent` cho Project 2 tại Branch. Mininet scale down để demo ổn định:

- Project 1: 20 user.
- Project 2: 20 user, chia 10 HQ + 10 Branch.
- Project 3: 20 user.
- Project 4: 20 user.
- IT Support: 10 user.

Tổng corporate user runtime: **90**.

## SDN boundary

OS-Ken chỉ quản lý 6 Open vSwitch:

- `access_floor1`
- `access_floor2`
- `core_hq`
- `access_branch`
- `dist_branch`
- `infra_access`

CE bridge, MPLS L2VPN bridge, firewall, `ipsec_l3` và Internet/Partner service zone không phải OpenFlow target.

## Entry point chính thức

Topology v7 chạy từ:

```bash
sudo ./sdn_mpls_demo/run_topology.sh
```

Script gọi `sdn_mpls_demo/topology_enterprise_v7.py`. `topology_hybrid_sdn.py` chỉ còn để reuse helper/control-agent đã ổn định và giữ lịch sử migration; nó không còn là executable topology chính.

## Acceptance tối thiểu

`./scripts/start_demo.sh` chạy `scripts/mininet_dashboard_preflight.py`, kiểm tra:

- VLAN 93 HQ -> Branch.
- VLAN 93 Branch -> HQ.
- Project 1 bị cách ly khỏi Project 3.
- Project 1 truy cập Partner PBX qua firewall.
- Branch IoT truy cập HQ Monitoring qua `fw_telesale -> ipsec_l3 -> fw_hq`.
- Guest bị cách ly khỏi Project 2.

Preflight coi L2VPN Backup `down/standby` là **đúng thiết kế**.

## Những điều không được tuyên bố

Không được ghi rằng lab đã chứng minh nếu chưa có evidence riêng:

- MPLS provider control plane thật.
- IPsec cryptographic tunnel thật.
- Stateful firewall HA failover giữa hai appliance thật.
- StackWise/VSS/MLAG/FHRP production behavior.
- Carrier-grade L2VPN protection signaling.

Các phần trên được biểu diễn ở mức **logical design / runtime abstraction** để sơ đồ và demo nhất quán mà không phóng đại khả năng của Mininet/OVS.
