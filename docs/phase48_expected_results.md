# Phase 48 expected results — Full-SDN

> **Legacy / Historical Reference** — Kết quả kỳ vọng theo mốc triển khai; số liệu hiện hành nằm trong [Testing và acceptance](testing_and_acceptance.md).

| Nhóm | Kết quả mong đợi |
|---|---|
| Fabric | 6/6 OVS connected, OpenFlow 1.3, zero `OFPP_NORMAL` |
| Pipeline | Table `0 → 10 → 20 → 30` và default-deny |
| Policy | same-project allow; cross-project deny; Guest/IoT/IT least privilege |
| Anti-spoofing | invalid Port/VLAN/Subnet IP source bị drop |
| DHCP | Discover/Request relay và Offer/Ack trả đúng client |
| Forwarding | explicit L2/L3 action, VLAN push/pop, L3 rewrite khi cần |
| Resilience | VLAN 93 reachable trên Primary, Backup và sau restore |
| Tests | 24/24 Full-SDN unit, 27/27 live traffic |
| Failure | exit khác 0, không sửa expected hoặc biến BLOCKED thành PASS |

Live result chỉ hợp lệ tại thời điểm chạy trên Ubuntu runtime.
