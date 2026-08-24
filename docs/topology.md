# Topology

Repo hiện có **hai lớp mô tả khác nhau** và không được trộn lẫn:

1. **Thiết kế logic doanh nghiệp mục tiêu** dùng cho báo cáo/thuyết minh kiến trúc.
2. **Runtime Mininet hiện tại** dùng để chạy demo SDN/MPLS và kiểm thử.

## Thiết kế logic doanh nghiệp mục tiêu

Sơ đồ đã duyệt hiện tại:

- `docs/assets/enterprise_logical_topology_v7.svg`

Đặc điểm chính của thiết kế mục tiêu:

- Chỉ có **HQ + 1 Branch**.
- Cả HQ và Branch dùng **2-tier Collapsed Core / Distribution**.
- Mỗi site có cặp Firewall HA, 2 ISP và local Internet breakout.
- Corporate traffic HQ ↔ Branch dùng **IPsec L3 VPN qua Internet**.
- Mỗi site có **2 CE**; MPLS L2VPN có đường chính và dự phòng.
- Dự án dùng chung là **VLAN 93**, subnet `10.10.93.0/24`.
- Gateway VLAN 93 là `10.10.93.1` tại HQ; Branch không có SVI/gateway local cho VLAN 93.
- Chỉ VLAN 93 được mở rộng Layer 2 giữa HQ và Branch.
- CRM/PBX thuộc hệ thống đối tác và được biểu diễn ngoài Server Farm nội bộ.
- Server nội bộ tập trung tại HQ: AD, DNS, DHCP, File, NMS/Monitoring, Backup.

Sơ đồ logic cố ý không khẳng định cách dual-homing vật lý giữa Core-Dist pair và CE pair. Chi tiết failover, multi-chassis, port-channel hoặc cơ chế của nhà cung cấp phải được xác nhận theo thiết bị/dịch vụ thực tế trước khi triển khai.

## Runtime Mininet hiện tại

**Runtime chưa đồng bộ với thiết kế logic v7.** Nguồn cấu hình runtime hiện vẫn là `vars/network_model.yml` cùng các file `vars/*.yml` liên quan.

Runtime hiện tại còn sử dụng mô hình cũ:

- kiến trúc Access → Distribution → Core riêng tại HQ;
- Project C dùng VLAN 40, subnet `172.16.40.0/24`;
- một CE logic tại mỗi site;
- một firewall namespace tại mỗi site;
- MPLS Primary/Backup cho routed transport;
- transparent VPWS/E-Line bridge cho VLAN 40;
- chưa có IPsec HQ ↔ Branch trong runtime.

Sơ đồ runtime rút gọn hiện tại vẫn là:

- `docs/assets/sdn_mpls_runtime_topology.svg`

Do đó **không được dùng sơ đồ v7 làm bằng chứng rằng Mininet đã triển khai VLAN 93, dual CE, firewall HA hay IPsec**. Các phần này hiện là target/design intent cho đến khi source-of-truth, Mininet, dashboard và test suite được refactor.

## Nguyên tắc source of truth

- `vars/network_model.yml` là source of truth cho **runtime hiện tại**.
- `docs/assets/enterprise_logical_topology_v7.svg` là source of truth hình ảnh cho **kiến trúc mục tiêu**.
- Dashboard runtime không được tự suy ra trạng thái live từ các object design-only.
- Khi refactor runtime sang v7, phải cập nhật đồng bộ model, VLAN/routing/firewall vars, Mininet builder, frontend topology và tests trước khi tuyên bố hai lớp này khớp nhau.

## Khoảng cách cần xử lý để runtime khớp v7

Các thay đổi tối thiểu cần thực hiện trong phase migration tiếp theo:

1. Đổi project/VLAN plan sang Dự án 1/2/3/4 với VLAN 101/93/103/104 và các VLAN hạ tầng đã duyệt.
2. Đổi VLAN stretched từ 40 sang 93, subnet sang `10.10.93.0/24`, gateway `10.10.93.1` tại HQ.
3. Chuyển mô hình HQ từ 3 lớp sang 2-tier collapsed core/distribution; Branch cũng biểu diễn pair 2-tier.
4. Bổ sung design/runtime contract cho 2 CE mỗi site và primary/standby MPLS L2VPN mà không tạo loop Layer 2.
5. Bổ sung firewall HA design cho cả HQ và Branch; runtime có thể vẫn dùng một namespace/pair abstraction nếu ghi rõ giới hạn.
6. Bổ sung corporate IPsec L3 VPN qua Internet cho AD/DNS/DHCP relay/File/NMS/management traffic.
7. Đưa CRM/PBX ra Partner Network thay vì mô tả như internal PBX/CRM server tại HQ.
8. Cập nhật `TopologyCanvas.tsx`, API payload, packet paths và labels để không còn hard-code VLAN 40/Project C/three-layer topology.
9. Cập nhật toàn bộ tests và các `EXPECTED_*` trong `scripts/network_model.py`.
10. Chỉ sau khi test pass mới thay runtime diagram và README để tuyên bố hệ thống chạy đúng v7.

## Lưu ý mô phỏng

Thiết kế v7 là logical enterprise architecture, không phải cam kết rằng lab sẽ mô phỏng đầy đủ MPLS provider control plane, firewall appliance HA, FHRP/MLAG/StackWise hay carrier failover protocol. Mọi phần rút gọn phải được ghi rõ là logical/design-only để tránh trình bày sai khả năng của Mininet/OVS.
