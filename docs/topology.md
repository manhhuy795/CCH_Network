# Enterprise Full-SDN topology

Sơ đồ canonical:

![Enterprise Full-SDN topology](assets/enterprise_logical_topology_v7.svg)

Source of truth: `vars/network_model.yml`.

## Inventory

| Site | Controlled OVS | Endpoint groups |
|---|---|---|
| HQ | `access_floor1`, `access_floor2`, `core_hq`, `infra_access` | Project 1/2/3/4, IT Support, Guest, HQ IoT, Infrastructure |
| Branch | `access_branch`, `dist_branch` | Project 2 VLAN 93, Branch IoT VLAN 50 |

OS-Ken Controller dùng OpenFlow 1.3 tới đúng **6 OVS**. CE/L2VPN bridges, firewall namespaces và Internet/Partner zone không phải controller target.

## Runtime scale

| Nhóm | VLAN | Số lượng |
|---|---:|---:|
| Project 1 | 101 | 20 user |
| Project 2 | 93 | 20 user: 10 HQ + 10 Branch |
| Project 3 | 103 | 20 user |
| Project 4 | 104 | 20 user |
| IT Support | 110 | 10 user |
| Guest | 120 | 2 endpoint |
| HQ IoT | 140 | 5 endpoint |
| Branch IoT | 50 | 2 endpoint |

Tổng corporate users: **90**. Ngoài ra lab có 7 infrastructure services và 5 Internet/Partner service simulators.

## VLAN 93

- Subnet: `10.10.93.0/24`.
- Gateway duy nhất: `10.10.93.1` tại HQ.
- Branch không có SVI VLAN 93.
- Primary: `core_hq → ce_hq1 → l2vpn_primary → ce_branch1 → dist_branch`.
- Backup: `core_hq → ce_hq2 → l2vpn_backup → ce_branch2 → dist_branch`.
- Backup attachment path ở standby khi Primary healthy.
- Fail/recover Primary attachment link kích hoạt chuyển path tự động trong lab.

## Infrastructure và DHCP

VLAN 100 gắn vào `infra_access` gồm DHCP, DNS, AD, File, NMS, Backup và NTP. DHCP server là `10.10.100.10`; controller relay Discover/Request và trả Offer/Ack về đúng client attachment.

## Firewall/Internet

`fw_hq` và `fw_telesale` là nftables namespace đại diện firewall boundary của từng site. Internet/Partner services gồm PBX/Contact Center, CRM, Internet App simulator, Social Media simulator và General Internet service.

Runtime chỉ chứng minh forwarding/policy qua các boundary này; không chứng minh appliance HA, cryptographic IPsec hoặc carrier MPLS control plane.

## Entry points

```bash
./sdn_mpls_demo/run_controller.sh
sudo ./sdn_mpls_demo/run_topology.sh
./scripts/start_demo.sh
```

Topology executable chính là `sdn_mpls_demo/topology_enterprise_v7.py`.
