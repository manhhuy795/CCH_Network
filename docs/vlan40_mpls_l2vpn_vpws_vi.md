# Legacy — VLAN 40 MPLS L2VPN

Tài liệu này thuộc topology trước enterprise v7 và **không còn là thiết kế hiện hành**.

Thiết kế hiện tại đã chuyển shared project sang:

- VLAN `93`
- subnet `10.10.93.0/24`
- gateway `10.10.93.1` tại HQ
- MPLS L2VPN Primary/Backup với hai CE mỗi site

Tài liệu thay thế:

- `docs/vlan93_mpls_l2vpn_vpws_vi.md`
- `docs/topology.md`
- `docs/assets/enterprise_logical_topology_v7.svg`

Không dùng VLAN 40/`172.16.40.0/24` trong báo cáo hoặc acceptance mới.
