# Kiến trúc hệ thống v7

## Phạm vi

CCH_Network là lab logic cho kiến trúc Call Center/BPO gồm HQ + 1 Branch. Hệ thống kết hợp Network Automation, SDN/OpenFlow, firewall nftables, MPLS L2VPN behavior và routed intersite tunnel abstraction.

Đây không phải cấu hình production hoàn chỉnh và không mô phỏng provider MPLS control plane hoặc cryptographic IPsec.

## Lớp kiến trúc

- **Network Automation**: `vars/`, `templates/`, `inventories/`, `playbooks/`, `scripts/`, `generated_configs/`.
- **Data plane lab**: Mininet hosts/namespaces, 6 controlled OVS, transparent CE/L2VPN bridges, firewall namespaces và service simulators.
- **Control plane**: OS-Ken điều khiển OpenFlow 1.3 trên 6 OVS; controller không nằm trên data path.
- **Operations plane**: FastAPI, React dashboard, control-agent Unix socket và runtime evidence.

## HQ

HQ dùng 2-tier collapsed Core/Distribution. Runtime dùng `core_hq` làm một logical OVS đại diện cho cặp Core/Distribution HA trong thiết kế.

Các VLAN chính:

- VLAN 101 — Project 1.
- VLAN 93 — Project 2 shared HQ + Branch.
- VLAN 103 — Project 3.
- VLAN 104 — Project 4.
- VLAN 100 — Infrastructure server farm.

Gateway VLAN 93 là `10.10.93.1` tại HQ.

## Branch

Branch dùng `dist_branch` làm collapsed Core/Distribution runtime abstraction.

- VLAN 93 — Project 2, **không có SVI tại Branch**.
- VLAN 50 — Branch IoT, routed local gateway `10.20.50.1`.

## MPLS L2VPN

Chỉ VLAN 93 được Layer-2 stretch.

Primary:

```text
core_hq -> ce_hq1 -> l2vpn_primary -> ce_branch1 -> dist_branch
```

Backup:

```text
core_hq -> ce_hq2 -> l2vpn_backup -> ce_branch2 -> dist_branch
```

CE/L2VPN nodes là Linux bridge abstraction. Backup path được giữ standby để tránh loop Layer 2.

## Routed intersite / IPsec abstraction

Non-VLAN93 traffic đi theo kiến trúc:

```text
HQ Core-Dist -> Firewall HQ -> IPsec overlay -> Firewall Branch -> Branch Core-Dist
```

Runtime biểu diễn tunnel bằng:

```text
fw_hq -> ipsec_l3 -> fw_telesale
```

`ipsec_l3` chỉ chứng minh routed path behavior giữa hai firewall namespaces. Không có IKE/ESP/XFRM hoặc cryptographic proof. VLAN 93 không được route qua tunnel này.

## DHCP tập trung

DHCP Server là `10.10.100.10` tại HQ. DHCP relay được khai báo trong `vars/routing.yml` và được sinh vào candidate Cisco config:

- HQ: VLAN 93, 101, 103, 104, 110, 120, 140.
- Branch: VLAN 50.
- Branch không có SVI VLAN 93 nên không có DHCP relay cho VLAN 93 tại Branch.

## Firewall và Internet

- HQ local breakout qua `fw_hq`.
- Branch local breakout qua `fw_telesale` (runtime compatibility name cho firewall Branch).
- Mỗi namespace nftables đại diện cho active firewall HA cluster của site.
- Hai firewall có logical tunnel attachment cho routed intersite traffic.
- HQ và Branch có circuit ISP Primary/Backup riêng; object Primary/Backup dùng chung trong automation chỉ là role, không phải một circuit vật lý dùng chung.
- Project 2 Branch dùng gateway tại HQ, nên Internet/Partner traffic của VLAN 93 về HQ trước khi breakout.

## Security boundary

- Project VLANs bị cách ly lẫn nhau.
- Project chỉ được truy cập DHCP, DNS, AD, File và NTP trong Server VLAN 100.
- Guest chỉ được bootstrap services và General Internet.
- HQ/Branch IoT chỉ được các infrastructure service đã khai báo.
- Candidate config không tự suy diễn Port-channel, StackWise, VSS, MLAG hay cơ chế multi-chassis khi platform chưa được xác nhận.

## Partner services

- `h90` — Partner PBX / Contact Center.
- `hcall` — Partner CRM.

Các service này nằm ngoài Server Farm nội bộ.

## Source of truth

`vars/network_model.yml` là nguồn topology runtime chính. VLAN, routing, firewall và interface mapping phải đồng bộ với nó.

Dashboard không được biến design-only object thành runtime evidence. Mọi trạng thái live phải đến từ control agent, OVS, nftables hoặc runtime report.
