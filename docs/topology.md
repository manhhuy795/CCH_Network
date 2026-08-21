# Topology

Nguồn cấu hình chuẩn là `vars/network_model.yml`. Dashboard và Mininet phải đọc
cùng mô hình này; hình vẽ không được dùng làm nguồn dữ liệu runtime.

- Sơ đồ kiến trúc doanh nghiệp đã duyệt: `docs/assets/sdn_mpls_topology_it_support.svg`.
- Sơ đồ runtime Mininet rút gọn: `docs/assets/sdn_mpls_runtime_topology.svg`.

## HQ

- Floor 1: Project A VLAN 20, một nửa Project B VLAN 30, IoT VLAN 110 và Guest
  VLAN 120 đi qua `access_floor1` → `dist_hq_1`.
- Floor 2: một nửa Project B VLAN 30, 10 endpoint Project C VLAN 40, BackOffice
  VLAN 60 và IT Support VLAN 70 đi qua `access_floor2` → `dist_hq_2`.
- `core_hq` là core L3 logic đại diện cho cặp core HA trong thiết kế. Node này
  giữ gateway `172.16.40.1` của Project C.
- `infra_access` nối PBX/SBC VLAN 90 và chín dịch vụ hạ tầng VLAN 100.
- `ce_hq` là CE cho lưu lượng routed liên site. `fw_hq` chỉ phục vụ local
  Internet breakout, không nằm trên đường MPLS liên site.

## Branch Telesale

- 10 endpoint Project C VLAN 40, Telesale VLAN 50 và IoT VLAN 111 đi qua
  `access_branch` → `dist_branch`.
- `ce_telesale` là CE cho lưu lượng routed liên site.
- `fw_telesale` chỉ phục vụ local Internet breakout.

## VLAN 40 Project C — MPLS L2VPN logic

- Project C có tổng cộng 20 endpoint: 10 tại HQ và 10 tại Branch Telesale.
- Hai phía dùng cùng VLAN 40, subnet `172.16.40.0/24` và broadcast domain.
- Gateway tập trung tại HQ: `172.16.40.1` trên `core_hq`.
- Attachment circuit logic:
  - HQ: `dist_hq_2` → demarcation `ce_hq` → `d2-eth40` / `pw40-hq`.
  - Branch: `dist_branch` → demarcation `ce_telesale` → `bd-eth40` / `pw40-br`.
- Đường trình bày: `dist_hq_2 → ce_hq → l2vpn_vpws40 → ce_telesale → dist_branch`.
- `l2vpn_vpws40` ánh xạ sang Linux bridge `l2vpn40` để mô phỏng Ethernet
  trong suốt kiểu VPWS/E-Line. Runtime rút gọn service instance tại CE vào hai
  cổng bridge; CE không được tuyên bố là PE/P MPLS thật.
- Lab không giả lập MPLS label stack, PE/P router, LDP, RSVP hoặc BGP signaling.

## MPLS L3 transport

- Lưu lượng routed giữa hai site đi qua CE → MPLS → CE.
- `mpls_primary` dùng metric 10; `mpls_backup` dùng metric 100.
- Primary down thì chuyển sang Backup; cả hai down thì liên site routed không
  khả dụng.
- Không tạo IPSec, GRE hoặc static route trỏ trực tiếp CE này sang CE kia.

## Internet và SDN boundary

- Mỗi site có firewall breakout riêng tới `internet_zone`.
- OS-Ken chỉ quản lý tám Open vSwitch: `access_floor1`, `access_floor2`,
  `dist_hq_1`, `dist_hq_2`, `core_hq`, `access_branch`, `dist_branch` và
  `infra_access`.
- CE router, firewall, MPLS transport và L2VPN bridge không phải OpenFlow target.
- ISP circuit và firewall HA peer trong phần design contract là metadata
  thiết kế, không được đưa vào runtime node hoặc packet path.
