# Dashboard SDN trực tiếp

Dashboard FastAPI thao tác trực tiếp với Mininet và Open vSwitch. Kết quả ping,
iperf, OpenFlow và KPI thoại được lấy từ lab đang chạy, không dùng dữ liệu giả.
Sơ đồ CE/MPLS biểu diễn kiến trúc logic; Mininet hiện dùng một OVS trung tâm và
không mô phỏng control-plane/data-plane MPLS của nhà cung cấp.

## Khởi chạy trên Ubuntu VM

Terminal 1, chạy Mininet:

```bash
cd ~/Downloads/CCH_Network
sudo mn -c
./sdn_demo/run_demo.sh
```

Giữ nguyên cửa sổ có dấu nhắc `mininet>`.

Terminal 2, chạy dashboard:

```bash
cd ~/Downloads/CCH_Network
chmod +x dashboard/run_live_dashboard.sh
./dashboard/run_live_dashboard.sh
```

Mở `http://127.0.0.1:8000`. Khi truy cập từ máy Windows, dùng
`http://<IP-của-Ubuntu-VM>:8000`.

## Chức năng

- Sơ đồ Hybrid MPLS L3VPN + SDN Edge Policy được dựng bằng SVG.
- Animation gói tin chạy qua từng node/link thật trên sơ đồ.
- Liên site đi qua CE Branch → MPLS Cloud → CE HQ; Internet đi qua firewall
  riêng của từng site.
- Controller chỉ có control-plane tới các OVS, không điều khiển CE/MPLS Cloud.
- Ping và đo băng thông TCP/UDP trong namespace Mininet.
- Đo chất lượng Call Center bằng RTT, jitter, mất gói, thông lượng và MOS.
- Chặn hoặc gỡ chặn cặp host bằng flow OpenFlow ưu tiên 500.
- Đọc và diễn giải bảng flow trực tiếp từ `ovs-ofctl`.

Ngưỡng chất lượng thoại dùng trong lab:

| Chỉ số | Ngưỡng đạt |
|---|---:|
| RTT trung bình | ≤ 150 ms |
| Jitter UDP | ≤ 30 ms |
| Mất gói | ≤ 1% |
| MOS ước lượng | ≥ 4.0 |
| Thông lượng UDP | ≥ 0.1 Mbps |

MOS là giá trị ước lượng bằng E-model đơn giản từ các số đo mạng thật, phù hợp
cho demo học tập; đây không phải thiết bị đo kiểm VoIP chuyên dụng.

## API chính

```text
GET  /api/topology
GET  /api/flows
GET  /api/live/status
POST /api/test/ping
POST /api/test/iperf
POST /api/test/call-quality
POST /api/live/block
POST /api/live/unblock
```

Nếu web không tìm thấy namespace host, hãy kiểm tra terminal Mininet vẫn đang
ở dấu nhắc `mininet>` và chạy dashboard bằng script được cung cấp.
