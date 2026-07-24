# Thiet ke Hybrid MPLS L3VPN + SDN Edge Policy

## Ranh gioi dieu khien

OS-Ken dieu khien dung tam OVS bang OpenFlow 1.3:

- `access_floor1`, `access_floor2`
- `dist_hq_1`, `dist_hq_2`, `core_hq`
- `infra_access`, `access_branch`, `dist_branch`

CE, MPLS logic cloud va firewall khong thuoc OpenFlow control domain:

- CE: `ce_hq`, `ce_telesale`
- WAN: `mpls_primary`, `mpls_backup`
- Firewall: `fw_hq`, `fw_telesale`

Controller chi la control path. No khong nam tren data path cua packet.

## Data path

- User HQ di qua access, distribution, `core_hq` roi toi dich vu HQ.
- User Telesale di qua `access_branch`, `dist_branch`, `ce_telesale`, WAN
  primary hoac backup, `ce_hq`, roi vao vung dich vu HQ.
- Internet local breakout di tu mang nguoi dung qua firewall cua chinh site:
  `fw_hq` hoac `fw_telesale`.
- Luu luong lien site khong di qua firewall Internet; firewall chi xu ly
  local Internet breakout va inbound Internet policy.

## Policy

- VLAN 20/30/40 duoc co lap tai `core_hq`.
- VLAN 50 va VLAN 60 duoc co lap theo chieu nguon tai `dist_branch` va
  `core_hq`.
- Voice, Zalo, Call App/CRM va Internet duoc cap theo policy.
- Social Media bi chan, ke ca IT Support.
- Guest chi duoc truy cap Internet va mot so dich vu ha tang.
- IoT HQ/Telesale chi duoc toi DHCP/DNS/NTP va monitoring/NVR duoc cap.
- Default deny cho traffic khong match policy.

## Kiem tra runtime

```bash
python3 scripts/validate_redesigned_topology.py
sudo bash scripts/phase_topology_redesign_acceptance.sh
sudo ovs-ofctl -O OpenFlow13 dump-flows core_hq
sudo ovs-ofctl -O OpenFlow13 dump-flows dist_branch
```

Mininet, Open vSwitch, OS-Ken, firewall va link failover phai duoc kiem tra
tren Ubuntu. Kiem tra tinh tren Windows khong duoc tuyen bo la runtime PASS.
