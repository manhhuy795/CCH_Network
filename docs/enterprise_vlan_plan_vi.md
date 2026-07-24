# Ke hoach VLAN Enterprise

VLAN 10 danh cho Management va khong duoc tai su dung cho zone enterprise.

| VLAN | Zone | Subnet | Gateway | Switch |
|---:|---|---|---|---|
| 100 | Infrastructure Services | `172.16.100.0/24` | `172.16.100.1` | `infra_access` |
| 110 | IoT HQ / UPS HQ | `172.16.110.0/24` | `172.16.110.1` | `access_floor1` |
| 111 | IoT Branch / UPS Branch | `172.16.111.0/24` | `172.16.111.1` | `access_branch` |
| 120 | Guest HQ Floor 1 | `172.16.120.0/24` | `172.16.120.1` | `access_floor1` |

VLAN 110 va 111 cung role `iot` nhung la hai subnet routed rieng. Khong co
L2 VLAN stretching IoT qua MPLS. Guest chi o HQ Floor 1.

## Endpoint

- Guest: `guest_01`, `guest_02`.
- IoT HQ: `iot_cam_01`, `iot_cam_02`, `ups_floor1`, `ups_core_1`, `ups_core_2`.
- IoT Branch: `iot_branch_cam_01`, `ups_branch_1`.
- Infrastructure: `hdhcp`, `hdns`, `hntp`, `hmonitor`, `hnvr`, `hrecording`,
  `hdialer`, `hbackup`, `had` tren VLAN 100.

Tong inventory: 110 user + 5 public/service endpoint + 9 Guest/IoT/UPS + 9
infrastructure endpoint.

## Least privilege

- Guest duoc DHCP/DNS/NTP va General Internet; internal access bi deny.
- IoT/UPS chi duoc bootstrap va monitoring/NVR da khai bao; khong truy cap
  user, Guest, Voice hoac Internet.
- IT Support remote user theo policy, khong bypass Social Media.
- Internet/service inbound unsolicited bi firewall stateful chan.

Runtime Mininet hien giu IP reservation/static cho endpoint de test deterministic.
DHCP relay contract duoc khai bao tai `sdn_mpls_demo/policy.yml`; lease live chi
duoc ket luan khi `scripts/test_dhcp_runtime.py` tim thay DHCP daemon va lease
evidence that.
