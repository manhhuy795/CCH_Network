# Dashboard Hybrid MPLS L3VPN + SDN

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
cd dashboard/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo -E .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
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

- Mininet có 100 user thật nhưng sơ đồ gom thành 5 nhóm.
- MPLS Cloud là WAN transport mô phỏng, không phải MPLS provider-grade.
- Controller không điều khiển CE, Firewall hoặc MPLS Cloud.
- Link failure/reroute hiện là mô phỏng logic trên dashboard.
