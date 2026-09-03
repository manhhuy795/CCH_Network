# ACL và segmentation design

`vars/acl_policies.yml` là source of truth cho policy intent; OpenFlow Table 20 là enforcement point trong Full-SDN runtime.

## Project isolation

| Source VLAN | Deny destination VLANs |
|---:|---|
| 101 | 93, 103, 104 |
| 93 | 101, 103, 104 |
| 103 | 93, 101, 104 |
| 104 | 93, 101, 103 |

Project chỉ được mở tới DHCP, DNS, AD, File và NTP trong VLAN 100 theo allowlist; NMS/Backup không mở mặc định.

## Guest và IoT

- Guest VLAN 120: DHCP/DNS/NTP + General Internet; deny internal.
- HQ IoT VLAN 140: DHCP/DNS/NTP/NMS; deny user lateral và Internet.
- Branch IoT VLAN 50: chỉ infrastructure services qua routed firewall abstraction; deny VLAN 93 và default-deny.

## IT Support

VLAN 110 được chủ động quản trị các nhóm endpoint trên protocol/port được duyệt. Traffic unsolicited từ user/Guest/IoT vào VLAN 110 bị drop. Đây là least-privilege access, không phải full bypass.

## Enforcement notes

- Port ↔ VLAN ↔ Subnet IP được kiểm tra ở Table 0/10.
- Table 20 default-deny xử lý policy miss.
- Dynamic 5-tuple return flow chỉ phục vụ phiên hợp lệ và có timeout.
- Không tuyên bố static MAC binding hoặc full Zero Trust.
