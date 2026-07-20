# Dashboard Hybrid MPLS L3VPN + SDN

Note: `fw_hq` va `fw_telesale` la **stateful nftables firewall** trong Mininet lab. Dashboard phai hien thi chung la Internet policy enforcement point, nhung khong dien giai thanh firewall appliance production.

Dashboard gồm:

- FastAPI backend tại cổng `8000`.
- React/TypeScript frontend tại cổng `5173`.
- Trang HTML tích hợp tại `http://127.0.0.1:8000` để dự phòng khi không cần
  chạy Node.js.

Kết quả ping, iperf3 và flow counter lấy trực tiếp từ Mininet/OVS. Packet path,
MPLS và link failure trên sơ đồ là lớp mô hình logic phục vụ giải thích kiến
trúc.

## Điều kiện

Chạy trước:

```bash
./sdn_mpls_demo/run_controller.sh
sudo ./sdn_mpls_demo/run_topology.sh
```

## Backend

```bash
./dashboard/run_live_dashboard.sh
```

Backend không crash khi Mininet chưa chạy; API trả trạng thái và thông báo lỗi
tiếng Việt.

## Frontend

```bash
cd dashboard/frontend
npm install
npm run dev -- --host 0.0.0.0
```

Mở `http://<IP-Ubuntu-VM>:5173`.

## API

```text
GET  /api/topology
GET  /api/policies
GET  /api/flows
GET  /api/metrics/current
GET  /api/live/status
POST /api/test/ping
POST /api/test/iperf
POST /api/test/call-quality
POST /api/simulate/path
POST /api/policy/toggle
POST /api/link/fail
POST /api/link/recover
WS   /ws/metrics
```

## Giới hạn

- Mininet có 110 user thật nhưng sơ đồ gom thành 6 nhóm, gồm phòng IT Support.
- MPLS L3VPN Logic Cloud là WAN transport mô phỏng, không phải MPLS provider-grade.
- Controller không điều khiển CE, Firewall hoặc MPLS L3VPN Logic Cloud.
- Link failure/reroute hiện là mô phỏng logic trên dashboard.
