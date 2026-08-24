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

Non-VLAN93 traffic dùng:

```text
HQ gateway -> ipsec_l3 -> Branch gateway
```

`ipsec_l3` chỉ chứng minh route/path behavior. Không có IKE/ESP/XFRM hoặc cryptographic proof.

## Firewall và Internet

- HQ local breakout qua `fw_hq`.
- Branch local breakout qua `fw_telesale` (runtime compatibility name cho firewall Branch).
- Mỗi namespace nftables đại diện cho active firewall HA cluster của site.
- Project 2 Branch dùng gateway tại HQ, nên Internet/Partner traffic của VLAN 93 về HQ trước khi breakout.

## Partner services

- `h90` — Partner PBX / Contact Center.
- `hcall` — Partner CRM.

Các service này nằm ngoài Server Farm nội bộ.

## Source of truth

`vars/network_model.yml` là nguồn topology runtime chính. VLAN, routing, firewall và interface mapping phải đồng bộ với nó.

Dashboard không được biến design-only object thành runtime evidence. Mọi trạng thái live phải đến từ control agent, OVS, nftables hoặc runtime report.
