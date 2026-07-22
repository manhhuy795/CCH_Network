# Nghiệm thu Dashboard Runtime trên Ubuntu/VMware

Tài liệu này dùng để nghiệm thu runtime thật của mô hình:

> Hybrid MPLS L3VPN Logic Simulation + SDN Edge Policy for Call Center BPO

Không dùng mock, kết quả Windows hoặc static test để đánh dấu runtime PASS.

Trạng thái tại thời điểm tạo tài liệu:

```text
DASHBOARD LIVE RUNTIME PARTIAL.
```

Chỉ đổi thành `DASHBOARD LIVE RUNTIME PASS` sau khi toàn bộ mục A-J bên dưới
được chạy thật trên Ubuntu VM và có artifact chứng minh.

## 1. Chuẩn bị

Khuyến nghị Ubuntu 24.04 LTS trên VMware. Dùng tối thiểu 2 terminal:

- Terminal 1 giữ topology và prompt `mininet>`.
- Terminal 2 chạy dashboard, health check, API test và thu artifact.

Cài dependency:

```bash
cd ~/Downloads/CCH_Network
git pull
chmod +x sdn_mpls_demo/*.sh scripts/*.sh
sudo ./sdn_mpls_demo/setup_ubuntu_24_04.sh
sudo apt install -y curl iperf3 jq openvswitch-switch mininet
```

Kiểm tra phiên bản:

```bash
python3 --version
node --version
npm --version
mn --version
ovs-vsctl --version
iperf3 --version
```

Tạo thư mục artifact. Thư mục này đã được Git bỏ qua:

```bash
cd ~/Downloads/CCH_Network
STAMP="$(date +%Y%m%d-%H%M%S)"
export ACCEPT_DIR="$PWD/runtime_reports/acceptance_$STAMP"
mkdir -p "$ACCEPT_DIR"/{logs,flows,screenshots}
printf '%s\n' "$ACCEPT_DIR"
```

Không chạy `set -x`. Không copy `logs/operator.token` vào artifact.

## 2. Khởi động lab

Terminal 1:

```bash
cd ~/Downloads/CCH_Network
sudo mn -c
sudo CCH_AUTO_TEST_POLICY=0 ./sdn_mpls_demo/run_topology.sh
```

Giữ terminal tại:

```text
mininet>
```

Terminal 2:

```bash
cd ~/Downloads/CCH_Network
./scripts/stop_demo.sh
./scripts/start_demo.sh --install
./scripts/check_demo_health.sh | tee "$ACCEPT_DIR/health.txt"
```

Nạp operator token vào biến shell nhưng không in ra:

```bash
TOKEN="$(< logs/operator.token)"
test -n "$TOKEN"
```

Mở dashboard trong Ubuntu:

```text
http://127.0.0.1:5173
```

Mở từ Windows host:

```bash
hostname -I
```

Sau đó truy cập `http://<IP_VM>:5173`.

## 3. Chạy smoke suite trước

Terminal 2:

```bash
cd ~/Downloads/CCH_Network
sudo ./scripts/dashboard_runtime_smoke_test.sh
```

Script phải tạo:

```text
runtime_reports/dashboard_runtime_<timestamp>.log
runtime_reports/dashboard_runtime_<timestamp>.json
```

Không tiếp tục kết luận PASS nếu smoke suite trả exit code khác `0`.

## A. Core Network

### A1. 110 user và 5 service

Trong Terminal 1:

```text
nodes
testpolicy
```

Kết quả bắt buộc:

- topology báo `110 user + 5 service`;
- `testpolicy` đạt `40/40`;
- không sửa expected result để né lỗi.

Lưu output terminal vào:

```text
$ACCEPT_DIR/logs/topology-startup.txt
$ACCEPT_DIR/logs/testpolicy-40-of-40.txt
```

### A2. Tám OVS kết nối controller

Terminal 2:

```bash
CONTROLLED_OVS=(
  access_hq_a access_hq_b access_hq_c access_hq_it
  voice_access core_hq access_telesale dist_telesale access_bo
)

for bridge in "${CONTROLLED_OVS[@]}"; do
  printf '%-18s ' "$bridge"
  sudo ovs-vsctl get-controller "$bridge"
done | tee "$ACCEPT_DIR/flows/controller-ownership.txt"
```

Cả tám bridge phải trả controller `tcp:127.0.0.1:6653`.

Kiểm tra boundary không thuộc OpenFlow domain:

```bash
for bridge in mpls_cloud internet; do
  printf '%-18s ' "$bridge"
  sudo ovs-vsctl get-controller "$bridge"
done | tee "$ACCEPT_DIR/flows/non-openflow-boundaries.txt"

for node in ce_hq ce_telesale fw_hq fw_telesale; do
  if sudo ovs-vsctl br-exists "$node"; then
    echo "FAIL $node khong duoc la OVS do controller quan ly"
  else
    echo "PASS $node khong phai controlled OVS"
  fi
done
```

`mpls_cloud` và `internet` không được có controller. CE và Internet Edge
Boundary không được bị vẽ hoặc vận hành như OpenFlow switch.

## B. Mininet Control Agent

### B1. HEALTH thật

```bash
sudo dashboard/backend/.venv/bin/python - <<'PY' \
  | tee "$ACCEPT_DIR/logs/agent-health.txt"
from dashboard.backend.app.mininet_control import health

result = health()
print(result)
raise SystemExit(0 if result.get("ok") else 1)
PY
```

### B2. Malformed request và client disconnect

Đoạn kiểm tra này không in control token:

```bash
sudo dashboard/backend/.venv/bin/python - <<'PY' \
  | tee "$ACCEPT_DIR/logs/agent-resilience.txt"
import json
import socket
import time
import uuid

from dashboard.backend.app.mininet_control import (
    CONTROL_SOCKET,
    CONTROL_TOKEN,
    health,
)

def exchange(payload: bytes, read_response: bool = True) -> bytes:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3)
        client.connect(str(CONTROL_SOCKET))
        client.sendall(payload)
        return client.recv(65536) if read_response else b""

malformed = exchange(b"{not-json}\n")
assert malformed, "Agent khong tra response cho malformed JSON"

valid = {
    "token": CONTROL_TOKEN,
    "command": "HEALTH",
    "request_id": uuid.uuid4().hex,
}
exchange((json.dumps(valid) + "\n").encode(), read_response=False)
time.sleep(0.5)

for index in range(50):
    result = health()
    assert result.get("ok"), f"HEALTH thu {index + 1} FAIL: {result}"

print("PASS malformed request khong giet agent")
print("PASS client disconnect khong giet agent")
print("PASS 50/50 HEALTH requests")
PY
```

Kiểm tra log:

```bash
if grep -E \
  'BrokenPipeError|Exception in thread cch-mininet-control|Traceback' \
  sdn_mpls_demo/runtime/mininet_control_agent.log; then
  echo "FAIL agent log co traceback"
else
  echo "PASS agent log khong co traceback"
fi
```

## C. Dashboard Health

```bash
curl -fsS http://127.0.0.1:8000/api/health \
  | tee "$ACCEPT_DIR/logs/api-health.json" \
  | python3 -m json.tool
```

Các thành phần bắt buộc:

- Controller: Online
- Backend: Online
- Mininet topology: Online
- Mininet Control Agent: Online
- Open vSwitch: Online
- WebSocket: Connected sau khi bấm `Bắt đầu` tại trang Hiệu năng

Backend chỉ listen port 8000 nhưng agent/controller/OVS lỗi không được hiển thị
toàn hệ thống là healthy.

## D. Ping thật và packet animation

Chạy từng case trên dashboard và đối chiếu bằng `mininet>`:

| Source | Destination | Kết quả |
|---|---|---|
| `h30_01` | `h90` | ALLOW |
| `h20_01` | `h30_01` | DENY tại `core_hq` |
| `h20_01` | `hsocial` | DENY tại `core_hq` |
| `h70_01` | `h20_01` | ALLOW |
| `h20_01` | `h70_01` | DENY tại `core_hq` |

Lệnh Mininet:

```text
h30_01 ping -c 3 h90
h20_01 ping -c 3 h30_01
h20_01 ping -c 3 hsocial
h70_01 ping -c 3 h20_01
h20_01 ping -c 3 h70_01
```

Yêu cầu UI:

- kết quả lấy từ namespace Mininet thật;
- path lấy từ backend;
- DENY dừng đúng `blocked_at`;
- packet không đi qua Controller;
- packet không đi qua link đang DOWN;
- hiển thị `policy`, `cookie`, `priority`, enforcement switch và lý do.

## E. UDP ba lần liên tiếp

Chạy trên dashboard:

```text
Source: h30_01
Destination: h90
Test: UDP Jitter
Duration: 5 giây
Số lần: 3
```

Mỗi lần phải có:

- throughput;
- jitter;
- packet loss;
- lost/total datagrams;
- duration và session ID;
- không có `Connection refused`.

Sau mỗi lần:

```bash
curl -fsS \
  -H "X-CCH-Operator-Token: $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"source":"h30_01","destination":"h90"}' \
  http://127.0.0.1:8000/api/test/ping
```

Sau lần thứ ba, chạy lại Agent HEALTH ở mục B1.

## F. TCP

Chạy trên dashboard:

| Source | Destination | Duration |
|---|---|---|
| `h30_01` | `h90` | 5 giây |
| `h20_01` | `hcall` | 5 giây |

Kết quả phải có throughput, transferred bytes, duration và session ID. Raw
output phải là output iperf3 thật, không phải số ngẫu nhiên hoặc JSON hardcode.

## G. Concurrency

Smoke suite đã kiểm tra tự động:

- hai iperf khác destination được chạy đồng thời;
- hai iperf cùng destination: request thứ hai nhận `IPERF_BUSY`;
- không port collision;
- không dùng global `pkill`.

Đối chiếu:

```bash
sudo ss -ltnup | grep iperf3 || true
curl -fsS \
  -H "X-CCH-Operator-Token: $TOKEN" \
  http://127.0.0.1:8000/api/live/iperf-sessions \
  | tee "$ACCEPT_DIR/logs/iperf-sessions.json" \
  | python3 -m json.tool
```

Sau khi test kết thúc không được còn session stale.

## H. Link Fail/Recover

Trên trang Topology:

1. Chọn link `project_a-access_hq_a`.
2. Xác nhận `Fail link`.
3. Ping `h20_01 -> h90`.
4. Kiểm tra ping thay đổi và packet dừng trước link DOWN.
5. Xác nhận `Recover link`.
6. Ping lại và kiểm tra phục hồi.

Đối chiếu trạng thái thật:

```bash
curl -fsS http://127.0.0.1:8000/api/live/status \
  | tee "$ACCEPT_DIR/logs/link-live-status.json" \
  | python3 -m json.tool
sudo ovs-vsctl show > "$ACCEPT_DIR/flows/ovs-after-link-test.txt"
```

Không đánh dấu PASS nếu UI chỉ đổi màu nhưng interface Mininet không đổi.

## I. Policy và OpenFlow

### I1. Toggle thành công

Trên dashboard:

1. Mở `Chính sách & OpenFlow`.
2. Toggle `Chặn Social Media`.
3. Xác nhận trạng thái `Applying`.
4. Chờ controller ACK và trạng thái `Applied`.
5. Dump flow trước/sau và chạy ping để chứng minh hành vi thay đổi.
6. Bật lại policy ban đầu và xác nhận `Applied`.

Dump flow:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows core_hq \
  > "$ACCEPT_DIR/flows/core_hq.txt"
sudo ovs-ofctl -O OpenFlow13 dump-flows dist_telesale \
  > "$ACCEPT_DIR/flows/dist_telesale.txt"
sudo ovs-ofctl -O OpenFlow13 dump-flows access_hq_a \
  > "$ACCEPT_DIR/flows/access_hq_a.txt"
sudo ovs-ofctl -O OpenFlow13 dump-flows access_telesale \
  > "$ACCEPT_DIR/flows/access_telesale.txt"
```

Kiểm tra cookie/priority quan trọng:

```bash
grep -E 'cookie=0x(1001|1002|1100|1200|1301|1304)' \
  "$ACCEPT_DIR/flows/core_hq.txt" \
  "$ACCEPT_DIR/flows/dist_telesale.txt"
```

HQ policy phải enforce tại `core_hq`; Branch policy phải enforce tại
`dist_telesale`. Không cài cùng một DROP/ALLOW lên mọi OVS.

### I2. Reload thất bại

Chỉ thực hiện trong cửa sổ test riêng:

1. Ghi PID controller và dừng riêng controller.
2. Giữ backend đang chạy.
3. Toggle một policy boolean.
4. Backend phải rollback `policy.yml`.
5. UI phải hiển thị `Failed`, không được hiển thị `Applied`.
6. Khởi động lại controller và kiểm tra tám OVS reconnect.

Lệnh hỗ trợ:

```bash
sudo ss -ltnp 'sport = :6653'
tail -n 120 logs/controller.log
tail -n 120 sdn_mpls_demo/runtime/controller.log
cat sdn_mpls_demo/runtime/policy_apply_status.json | python3 -m json.tool
```

Không xóa test hoặc đổi acceptance criteria nếu reload failure không hiện
đúng trạng thái.

## J. Browser Acceptance

Kiểm tra trực tiếp ở viewport 1366x768:

- không page-level horizontal overflow;
- sidebar, header và workspace không che nhau;
- keyboard điều hướng được;
- focus nhìn thấy rõ;
- confirmation dialog giữ focus, hỗ trợ Escape và trả focus;
- error state cho backend/agent/token/WebSocket rõ ràng;
- packet animation còn hoạt động và tuân theo path backend;
- Inspector Drawer mở được bằng node và link;
- bảng OpenFlow lọc/search/sort được;
- logs không hiển thị token;
- realtime metrics có empty/stale/reconnect state;
- `prefers-reduced-motion` làm giảm animation.

Chụp tối thiểu:

```text
$ACCEPT_DIR/screenshots/overview-1366x768.png
$ACCEPT_DIR/screenshots/ping-allow-animation.png
$ACCEPT_DIR/screenshots/ping-deny-blocked-at.png
$ACCEPT_DIR/screenshots/link-down.png
$ACCEPT_DIR/screenshots/policy-applied.png
$ACCEPT_DIR/screenshots/policy-failed.png
$ACCEPT_DIR/screenshots/openflow-table.png
$ACCEPT_DIR/screenshots/realtime-metrics.png
$ACCEPT_DIR/screenshots/error-agent-offline.png
```

## 4. Thu log cuối

```bash
cp logs/backend.log "$ACCEPT_DIR/logs/backend.log"
cp logs/frontend.log "$ACCEPT_DIR/logs/frontend.log"
cp logs/controller.log "$ACCEPT_DIR/logs/dashboard-controller.log" 2>/dev/null || true
cp sdn_mpls_demo/runtime/controller.log \
  "$ACCEPT_DIR/logs/controller.log"
cp sdn_mpls_demo/runtime/mininet_control_agent.log \
  "$ACCEPT_DIR/logs/mininet-control-agent.log"
cp sdn_mpls_demo/runtime/installed_flows.json \
  "$ACCEPT_DIR/flows/installed-flows.json"
sudo ovs-vsctl show > "$ACCEPT_DIR/flows/ovs-vsctl-show.txt"
```

Kiểm tra lỗi chưa xử lý:

```bash
grep -RniE \
  'BrokenPipeError|ConnectionResetError|Exception in thread|Address already in use|unhandled task exception|Traceback' \
  "$ACCEPT_DIR/logs" || true
```

Mỗi kết quả grep phải được phân tích. Không được bỏ qua traceback mới.

## 5. Bảng kết quả

Điền sau khi chạy thật:

| Nhóm | Kết quả | Artifact | Ghi chú |
|---|---|---|---|
| A. Core Network | PENDING | | |
| B. Control Agent | PENDING | | |
| C. Dashboard Health | PENDING | | |
| D. Ping | PENDING | | |
| E. UDP | PENDING | | |
| F. TCP | PENDING | | |
| G. Concurrency | PENDING | | |
| H. Link | PENDING | | |
| I. Policy/OpenFlow | PENDING | | |
| J. Browser | PENDING | | |

## 6. Điều kiện kết luận

Chỉ ghi:

```text
DASHBOARD LIVE RUNTIME PASS
```

khi:

- A-J đều PASS;
- `testpolicy` là 40/40;
- smoke suite exit code `0`;
- không có traceback mới chưa xử lý;
- artifact không chứa token hoặc secret;
- packet animation, flow, policy và link state khớp runtime thật.

Nếu còn bất kỳ mục PENDING hoặc FAIL nào, kết luận bắt buộc là:

```text
DASHBOARD LIVE RUNTIME PARTIAL.
```
