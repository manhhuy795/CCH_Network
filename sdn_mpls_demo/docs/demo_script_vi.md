# Kịch bản demo

## 1. Giới thiệu

“Đây là mô hình Hybrid MPLS L3VPN + SDN Edge Policy. MPLS vận chuyển traffic
giữa hai site; OS-Ken chỉ điều khiển các Open vSwitch ở hai đầu mạng.”

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

Chọn `h50_01 → h20_01`, bấm **Mô phỏng path**:

```text
Telesale → Branch Access → Branch Distribution → CE Branch
→ MPLS Cloud → CE HQ → HQ Core → Access HQ-A → Dự án A
```

Nhấn mạnh rằng controller không nối control-plane tới CE/MPLS Cloud.

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
