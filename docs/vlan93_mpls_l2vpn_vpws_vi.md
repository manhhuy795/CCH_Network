# VLAN 93 — MPLS L2VPN VPWS/E-Line Logic

## Mục tiêu

Dự án 2 cần cùng broadcast domain tại HQ và Branch. Vì vậy VLAN 93 được kéo Layer 2 qua MPLS L2VPN logic.

- VLAN: `93`
- Subnet: `10.10.93.0/24`
- Default gateway: `10.10.93.1`
- Gateway site: HQ
- Branch SVI VLAN 93: **không có**

## Primary / Backup

Primary:

```text
CORE-DIST-HQ
-> CE-HQ1
-> MPLS L2VPN Primary
-> CE-BR1
-> CORE-DIST-BR
```

Backup:

```text
CORE-DIST-HQ
-> CE-HQ2
-> MPLS L2VPN Backup
-> CE-BR2
-> CORE-DIST-BR
```

Runtime giữ Backup attachment path ở trạng thái standby/down khi Primary đang hoạt động. Cách này tránh tạo Layer-2 loop vì lab không giả lập carrier protection protocol hoặc multi-chassis control plane.

Khi một link Primary được fail qua Mininet control agent, runtime hạ toàn Primary path và bật Backup path. Khi recover Primary, runtime đưa Primary lên và trả Backup về standby.

## Mô phỏng Mininet

CE và L2VPN node là Linux bridge trong suốt:

- `ce_hq1`
- `ce_hq2`
- `ce_branch1`
- `ce_branch2`
- `l2vpn_primary`
- `l2vpn_backup`

Các OVS attachment port được đặt access VLAN 93. Bridge không định tuyến và không sở hữu gateway.

## Không mô phỏng

Lab không được coi là bằng chứng cho:

- PE/P router thật.
- MPLS label stack.
- LDP / RSVP.
- MP-BGP/VPLS/EVPN control plane.
- Carrier-grade pseudowire protection signaling.
- LACP/MC-LAG/StackWise/VSS behavior thật giữa CE và collapsed core pair.

## Acceptance

Case tối thiểu:

1. `h93_01` tại HQ ping `h93_11` tại Branch: PASS qua Primary.
2. `h93_11` ping `h93_01`: PASS.
3. Branch không có SVI/gateway VLAN 93.
4. Backup path ở standby khi Primary healthy.
5. Fail Primary -> Backup được bật và VLAN 93 tiếp tục reachable.
6. Recover Primary -> Primary hoạt động lại, Backup trở về standby.

Mọi báo cáo phải phân biệt rõ **Ethernet service behavior** với **provider MPLS implementation**.
