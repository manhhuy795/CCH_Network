# Thiết kế SDN Full-SDN

## Controller và switch fabric

`sdn_mpls_demo/controller_fabric.py` là OS-Ken OpenFlow 1.3 controller cho 6 OVS. Switch dùng `fail-mode=secure`; controller cài explicit output actions và không dựa vào `OFPP_NORMAL`.

## Pipeline bốn bảng

| Table | Chức năng | Chuyển tiếp hợp lệ |
|---:|---|---|
| 0 | Kiểm tra ingress port và VLAN | `goto_table:10` |
| 10 | ARP/IPv4 classification, Port ↔ VLAN ↔ Subnet IP anti-spoofing | `goto_table:20` |
| 20 | Project/Guest/IoT/IT policy, default-deny, dynamic 5-tuple return flow | `goto_table:30` |
| 30 | Explicit L2/L3 forwarding, VLAN push/pop, MAC rewrite, TTL decrement | output port |

ARP hợp lệ được xử lý có kiểm soát để phục vụ Proxy ARP và virtual gateway. IPv6 bị drop vì lab chỉ hỗ trợ IPv4.

## L2/L3 forwarding

Controller học endpoint theo VLAN, tính shortest path trong 6-OVS fabric và cài flow hai chiều trên mọi switch dọc đường đi. Với traffic được route, Table 30 áp MAC rewrite và giảm TTL. Trên biên access/trunk, controller dùng OpenFlow VLAN push/pop khi đường đi yêu cầu.

## Session return

Khi IT Support hoặc một luồng TCP/UDP hợp lệ khởi tạo phiên, controller có thể cài return flow priority cao hơn theo reverse 5-tuple:

```text
protocol + source IP + destination IP + source port + destination port
```

Flow có timeout và không biến thành broad reverse allow. Traffic unsolicited vẫn bị Table 20 drop.

## Security policy

- Same-project: allow.
- Cross-project: deny.
- Guest: DHCP/DNS/NTP và General Internet; deny internal.
- IoT: DHCP/DNS/NTP/NMS; deny user lateral và broad Internet.
- IT Support: quyền quản trị được khai báo; deny unsolicited reverse.
- Policy miss: deny.

## DHCP Relay

Controller theo dõi client attachment, relay DHCP request tới `hdhcp` trên `infra_access` và gửi response về đúng switch/port/VLAN của client. Unit suite kiểm tra Discover/Offer delivery; live DORA cần Ubuntu runtime và DHCP daemon thật.

## VLAN 93 failover

Topology agent quản lý trạng thái Primary/Backup attachment path. Controller theo dõi port/link state và purge selective VLAN 93 flows để forwarding được học/cài lại trên path active. Đây là attachment-link failover, không phải carrier-grade fast reroute.

## Không tuyên bố

- static Port ↔ MAC binding;
- full Zero Trust architecture;
- queue/DSCP/end-to-end QoS;
- provider MPLS control plane hoặc cryptographic IPsec;
- production readiness.
