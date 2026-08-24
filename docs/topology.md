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

Hệ thống chỉ có **HQ + 1 Branch**. Cả hai site dùng mô hình **2-tier Collapsed Core / Distribution** thay vì Access -> Distribution -> Core riêng như phiên bản cũ.

HQ có các nhóm chính:

- Dự án 1: VLAN 101, `10.10.101.0/24`.
- Dự án 2: VLAN 93, `10.10.93.0/24`.
- Dự án 3: VLAN 103, `10.10.103.0/24`.
- Dự án 4: VLAN 104, `10.10.104.0/24`.
- Server/Infrastructure: VLAN 100, gồm AD, DNS, DHCP, File, NMS/Monitoring, Backup và NTP phụ trợ.
- Office/IT Support, Guest và HQ IoT dùng VLAN riêng trong lab; các VLAN này được đánh dấu `implementation_choice` vì sơ đồ logic không chốt số VLAN cụ thể cho từng nhóm đó.

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

Trong Mininet, CE và MPLS L2VPN được biểu diễn bằng các Linux bridge trong suốt. Backup attachment path được giữ **standby/down** khi Primary hoạt động để không tạo Layer-2 loop. Khi Primary bị fail qua control agent, runtime chuyển sang Backup.

Lab **không** mô phỏng PE/P router, MPLS label stack, LDP/RSVP hoặc provider control plane. Vì vậy kết quả chỉ chứng minh Ethernet service behavior của VPWS/E-Line logic.

## IPsec L3 giữa HQ và Branch

Các mạng routed không phải VLAN 93 đi liên site qua `ipsec_l3`.

Runtime dùng một Linux router để mô phỏng **routed tunnel behavior**:

- HQ routed networks -> `ipsec_l3` -> Branch.
- Branch VLAN 50 -> `ipsec_l3` -> HQ services.
- VLAN 93 không được route qua IPsec.

Điểm quan trọng: runtime hiện **không** triển khai IKE, ESP, XFRM hay mã hóa IPsec thật. Dashboard/tài liệu chỉ được ghi là `IPsec L3 abstraction` hoặc `routed tunnel abstraction`, không được dùng nó làm bằng chứng cryptographic IPsec.

## Firewall và Internet breakout

Mỗi site có firewall HA trong thiết kế. Mininet không dựng hai appliance firewall độc lập cho mỗi site; thay vào đó:

- `fw_hq` là namespace nftables đại diện cho active firewall HA cluster tại HQ.
- `fw_telesale` là tên runtime giữ lại cho firewall Branch để tránh phá API cũ; về mặt thiết kế nó là firewall HA của Branch.

Internet breakout là local tại từng site. VLAN 93 dùng gateway tại HQ nên traffic Internet/Partner của Project 2 Branch đi theo L2VPN về HQ trước khi qua firewall HQ.

## Partner CRM/PBX

CRM và PBX/Contact Center không còn nằm trong Server Farm nội bộ.

- `h90`: Partner PBX / Contact Center.
- `hcall`: Partner CRM.

Hai service này nằm sau `internet_zone`/Partner Service Zone trong lab và được kiểm soát qua firewall như external/partner services.

## Runtime scale

Sơ đồ logic ghi khoảng `~70 Agent` cho Project 2 tại Branch. Mininet cố ý không tạo đủ 70 agent để tránh làm VM demo nặng không cần thiết.

Runtime hiện dùng:

- Project 1: 20 user.
- Project 2: 20 user, chia 10 HQ + 10 Branch.
- Project 3: 20 user.
- Project 4: 20 user.
- IT Support: 10 user.

Tổng corporate user runtime: **90**. Đây là scale-down lab, không phải số lượng production.

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

Script này gọi:

```text
sdn_mpls_demo/topology_enterprise_v7.py
```

`topology_hybrid_sdn.py` vẫn còn trong repository để giữ các helper/control-agent đã ổn định và làm lịch sử migration, nhưng không còn là executable entry point chính thức.

## Acceptance tối thiểu

`./scripts/start_demo.sh` chạy `scripts/mininet_dashboard_preflight.py`, kiểm tra các case v7:

- VLAN 93 HQ -> Branch.
- VLAN 93 Branch -> HQ.
- Project 1 bị cách ly khỏi Project 3.
- Project 1 truy cập Partner PBX qua firewall.
- Branch IoT truy cập HQ Monitoring qua routed `ipsec_l3` abstraction.
- Guest bị cách ly khỏi Project 2.

Preflight coi L2VPN Backup ở trạng thái `down/standby` là **đúng thiết kế**, không phải lỗi.

## Những điều không được tuyên bố

Không được ghi trong báo cáo rằng lab đã chứng minh các tính năng sau nếu chưa có evidence riêng:

- MPLS provider control plane thật.
- IPsec cryptographic tunnel thật.
- Stateful firewall HA failover giữa hai appliance thật.
- StackWise/VSS/MLAG/FHRP production behavior.
- Carrier-grade L2VPN protection signaling.

Các phần trên được biểu diễn ở mức **logical design / runtime abstraction** để sơ đồ và demo nhất quán mà không phóng đại khả năng của Mininet/OVS.
