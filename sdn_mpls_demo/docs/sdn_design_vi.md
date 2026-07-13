# Thiết kế Hybrid MPLS L3VPN + SDN Edge Policy

## Hai lớp của hệ thống

**Network Automation** sinh cấu hình VLAN, ACL, routing, firewall và CE cho
mạng doanh nghiệp. `vars/sdn.yml` cùng
`scripts/generate_sdn_policies.py` là lớp sinh intent/policy ở mức automation;
generic REST trong lớp này không được xem là OpenFlow Controller hoàn chỉnh.

**SDN runtime demo** dùng OS-Ken, Mininet và Open vSwitch. Khi OVS chưa có rule,
switch gửi Packet-In lên controller. Controller đọc `policy.yml`, quyết định
allow/drop rồi gửi Flow-Mod xuống OVS.

## Ranh giới điều khiển

Controller điều khiển:

- `access_hq_a`, `access_hq_b`, `access_hq_c`
- `voice_mgmt`, `core_hq`
- `access_branch`, `dist_branch`

Controller không điều khiển:

- `ce_hq`, `ce_branch`
- `mpls_cloud`
- `fw_hq`, `fw_branch`

MPLS L3VPN không bị SDN thay thế. Trong lab, MPLS Cloud là WAN transport logic
và không mô phỏng control-plane nhà cung cấp.

## Policy

- Cách ly VLAN 20/30/40.
- Cách ly VLAN 50/60.
- Cho phép Voice, Zalo, Call App và Internet test.
- Chặn Social Media.
- Cho phép có kiểm soát Telesale ↔ Dự án A để demo liên site.
- Default deny cho traffic không match policy.

## Đo kiểm

Dashboard chỉ đo cặp endpoint đang chọn:

- ping: RTT và packet loss.
- iperf3 TCP: throughput.
- iperf3 UDP: throughput, jitter và packet loss.
- ovs-ofctl: flow/packet/byte counter trên 8 OVS.

Link failure/reroute trên dashboard hiện là mô phỏng logic phục vụ demo. Phiên
bản này không cài fast-failover group hoặc giao thức định tuyến động.
