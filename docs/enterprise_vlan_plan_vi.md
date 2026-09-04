# Kế hoạch VLAN Enterprise Full-SDN

## VLAN theo sơ đồ logic hiện hành

| VLAN | Zone | Subnet | Gateway | Phạm vi |
|---:|---|---|---|---|
| 50 | Branch IoT | `10.20.50.0/24` | `10.20.50.1` | Branch only |
| 93 | Project 2 Shared | `10.10.93.0/24` | `10.10.93.1` tại HQ | HQ + Branch, MPLS L2VPN |
| 101 | Project 1 | `10.10.101.0/24` | `10.10.101.1` | HQ |
| 103 | Project 3 | `10.10.103.0/24` | `10.10.103.1` | HQ |
| 104 | Project 4 | `10.10.104.0/24` | `10.10.104.1` | HQ |

## VLAN implementation choice trong lab

Sơ đồ logic không chốt ID cụ thể cho Server Farm, Office/IT, Guest và HQ IoT. Runtime chọn các VLAN sau để mô phỏng nhất quán; đây là **implementation choice**, không phải yêu cầu business bắt buộc:

| VLAN | Zone | Subnet | Gateway |
|---:|---|---|---|
| 10 | Management | `10.10.10.0/24` | `10.10.10.1` |
| 100 | Server / Infrastructure | `10.10.100.0/24` | `10.10.100.1` |
| 110 | Office / IT Support | `10.10.110.0/24` | `10.10.110.1` |
| 120 | Guest HQ | `10.10.120.0/24` | `10.10.120.1` |
| 140 | HQ IoT / Camera / Printer / UPS | `10.10.140.0/24` | `10.10.140.1` |

## Quy tắc VLAN 93

- VLAN 93 là VLAN duy nhất được stretch Layer 2 giữa HQ và Branch.
- Branch **không có SVI VLAN 93**.
- Default gateway duy nhất là `10.10.93.1` tại HQ.
- Primary path dùng CE-HQ1 / MPLS L2VPN Primary / CE-BR1.
- Backup path dùng CE-HQ2 / MPLS L2VPN Backup / CE-BR2.
- Backup ở trạng thái standby để tránh L2 loop trong lab.

## Infrastructure service

VLAN 100 chứa:

- `hdhcp` — DHCP Server.
- `hdns` — DNS Server.
- `had` — Active Directory.
- `hfile` — File Server.
- `hmonitor` — NMS / Monitoring.
- `hbackup` — Backup Server.
- `hntp` — NTP phụ trợ cho lab.

CRM và PBX/Contact Center **không** nằm trong VLAN 100; chúng là partner services bên ngoài internal Server Farm.

## Least privilege

- Các Project VLAN bị cách ly lẫn nhau ở SDN enforcement point.
- Guest chỉ được bootstrap service cần thiết và General Internet.
- IoT chỉ được bootstrap/monitoring service đã khai báo.
- IT Support có quyền hỗ trợ có kiểm soát, không phải full bypass.
- Social Media vẫn bị chặn bởi firewall policy.
- Unsolicited Internet/Partner inbound bị stateful nftables firewall chặn.
