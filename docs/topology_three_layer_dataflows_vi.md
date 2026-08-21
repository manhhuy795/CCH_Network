# Topology ba lop va luong du lieu

## Mo hinh

Day la mo phong logic Hybrid MPLS L3VPN + SDN Edge Policy cho Call Center BPO.
Topology co ba lop tai HQ:

```text
Access Floor 1 -> Distribution HQ 1 -> Core HQ
Access Floor 2 -> Distribution HQ 2 -> Core HQ
Access Branch  -> Distribution Branch -> CE Telesale
```

`core_hq` la node runtime dai dien cho Core HQ Logical HA Pair. Lab khong fake
HSRP/VRRP/MLAG. Co 8 OVS duoc OS-Ken dieu khien: `access_floor1`,
`access_floor2`, `dist_hq_1`, `dist_hq_2`, `core_hq`, `access_branch`,
`dist_branch`, `infra_access`.

CE, firewall va MPLS cloud khong phai OpenFlow device. Controller chi nam tren
control path OpenFlow, khong nam trong data path cua packet.

## Phan bo tang va VLAN

| Khu vuc | Nhom | VLAN | Switch |
|---|---|---:|---|
| HQ Floor 1 | Project A | 20 | access_floor1 |
| HQ Floor 1/2 | Project B | 30 | access_floor1/access_floor2 |
| HQ Floor 1 | IoT HQ | 110 | access_floor1 |
| HQ Floor 1 | Guest HQ | 120 | access_floor1 |
| HQ Floor 2 | Project C | 40 | access_floor2 |
| HQ Floor 2 | BackOffice | 60 | access_floor2 |
| HQ Floor 2 | IT Support | 70 | access_floor2 |
| Branch | Telesale | 50 | access_branch |
| Branch | IoT Branch | 111 | access_branch |
| HQ service zone | PBX/SBC | 90 | infra_access |
| HQ service zone | DHCP/DNS/NTP/monitoring/NVR/CRM... | 100 | infra_access |

Project B dung chung VLAN/subnet nhung co placement tren hai access switch; path
thuc te cua host la nguon de animation, khong phai path hardcode trong React.

## Data flow

- Agent HQ -> Voice/CRM: Access -> Distribution -> Core -> `infra_access`.
- Telesale -> Voice/CRM: Access Branch -> Distribution Branch -> CE Branch ->
  MPLS Primary (metric 10) -> CE HQ -> Core -> `infra_access`.
- Khi Primary down, control agent doi link that sang Backup (metric 100). Khi
  Primary recover, policy failback. Hai cloud MPLS khong noi truc tiep voi nhau.
- HQ Internet: Core -> `fw_hq` -> Internet Zone. Branch Internet:
  Distribution Branch -> `fw_telesale` -> Internet Zone. Khong hairpin Internet
  Branch ve HQ.
- IoT HQ -> NVR/Monitoring: Access Floor 1 -> Distribution HQ -> Core ->
  `infra_access`.
- IoT Branch -> Monitoring: Access Branch -> Distribution Branch -> CE -> MPLS
  active -> CE HQ -> Core -> `infra_access`.
- UPS la endpoint duoc monitor, khong phai router/switch va khong duoc chen vao
  packet path cua user.

## Policy

Project A/B/C isolation, Branch Telesale/BackOffice isolation va user-to-IT
inbound deny duoc enforce bang OpenFlow tai Core/Distribution. Internet social
deny, inbound unsolicited va stateful session duoc enforce bang nftables tai
firewall site. Policy khong dung `any any`.

DHCP duoc mo ta voi server `hdhcp` VLAN 100 va relay gateway `core_hq`,
`dist_branch`. Runtime deterministic hien giu IP reservation/static cho host;
script `scripts/test_dhcp_runtime.py` se tra PENDING neu chua co lease evidence
thuc tu DHCP daemon. Khong duoc coi host IP static la DHCP lease.

## Gioi han

UDP iperf la phep uoc luong jitter/loss, khong thay the SIP/RTP production.
MPLS la transport logic, khong mo phong PE/P core that. Firewall la nftables
namespace trong Mininet, khong phai appliance production.
