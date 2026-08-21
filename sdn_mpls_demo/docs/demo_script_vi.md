# Kịch bản demo

## 1. Giới thiệu

“Đây là mô hình Hybrid MPLS L3VPN, MPLS L2VPN VPWS logic cho VLAN 40 và SDN Edge Policy. L3VPN vận chuyển các prefix routed; VPWS giữ cùng miền Ethernet cho Project C; OS-Ken chỉ điều khiển các Open vSwitch phía doanh nghiệp.”

## 2. Kiểm tra 110 user

Tại Mininet:

```text
nodes
```

Chỉ ra các host từ `h20_01` đến `h60_20` và `h70_01` đến `h70_10`.
Dashboard gom chúng thành 6 nhóm để
sơ đồ không bị rối nhưng dropdown vẫn chọn được từng user.

## 3. Cách ly Project

Chọn `h20_01 → h30_01`, bấm **Ping thực tế**:

- Kết quả mong đợi: fail.
- Điểm chặn: HQ Core SDN.
- Lý do: cách ly VLAN 20/30.

## 4. Voice và Call App

Chọn `h20_01 → h90`, sau đó `h20_01 → hcall`:

- Voice được allow và đánh dấu Voice Priority.
- Call App đi qua Firewall HQ.
- Bấm **Chất lượng thoại** để xem RTT, jitter, loss, throughput và MOS.

## 5. Branch và Internet

Chọn `h50_01 → hcall`: path đi qua Firewall Branch.

Chọn `h50_01 → hsocial`: traffic bị chặn tại Firewall Branch.

## 6. Liên site

Trước tiên chọn `h40_11 → h40_01`. Hai endpoint cùng VLAN/subnet nhưng khác site; path phải đi qua `access_branch → dist_branch → l2vpn_vpws40 → dist_hq_2 → access_floor2`. Nêu rõ bridge chỉ mô phỏng forwarding Ethernet, không mô phỏng nhãn MPLS hoặc PE/P control plane.

Hạ link `dist_branch-l2vpn_vpws40`: ping xuyên site phải fail. Khôi phục link: ping phải hoạt động lại. Đây là bằng chứng failure injection thật trên attachment circuit, không phải chỉ đổi trạng thái giao diện.

Chọn `h50_01 → h20_01`, bấm **Mô phỏng path**:

```text
Telesale → Branch Access → Branch Distribution
```

Kết quả mong đợi là **deny** tại Branch Distribution. Telesale không được ping ngang sang Project A/B/C.

Sau đó chọn `h70_01 → h50_01`, bấm **Mô phỏng path**:

```text
IT Support → Access HQ-IT → HQ Core → CE HQ
→ MPLS Cloud → CE Branch → Branch Distribution → Branch Access → Telesale
```

Nhấn mạnh rằng chỉ IT Support có quyền hỗ trợ liên site; controller không nối control-plane tới CE/MPLS Cloud.

## 7. Flow table

Mở bảng flow để xem switch, match, action, priority, packet/byte counter và lý
do tiếng Việt. Có thể đối chiếu bằng:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows core_hq
```

## 8. Link failure

Chọn một link trên sơ đồ và bấm nút mô phỏng lỗi. Nếu path cần link đó,
dashboard trả “Không có đường đi hợp lệ”. Đây là mô phỏng logic, không phải
reroute dataplane thật.
