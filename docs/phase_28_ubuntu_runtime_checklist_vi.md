# Phase 28: Pending Ubuntu Runtime Validation

Tai lieu nay dung de chay validation runtime tren Ubuntu VM. Khong danh dau Phase 28 la PASS neu chua chay that cac buoc ben duoi.

## 1. Dependency can kiem tra

```bash
cd ~/Downloads/CCH_Network
git pull
chmod +x sdn_mpls_demo/*.sh scripts/*.sh

python3 --version
node -v
npm -v
mn --version
ovs-vsctl --version
iperf3 --version
```

Neu thieu dependency:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git curl mininet openvswitch-switch iperf3
sudo systemctl enable --now openvswitch-switch
```

Voi Ubuntu 24.04/OS-Ken:

```bash
./sdn_mpls_demo/setup_ubuntu_24_04.sh
```

## 2. Chay static test tren Ubuntu

```bash
python3 scripts/validate_vars.py
python3 scripts/generate_configs.py
python3 scripts/verify_network.py
pytest -q
```

Frontend:

```bash
cd dashboard/frontend
npm ci
npm run build
cd ../..
```

## 3. Cleanup Mininet cu

```bash
sudo mn -c
sudo pkill -f topology_hybrid_sdn.py || true
sudo pkill -f os_ken.cmd.manager || true
```

## 4. Chay OS-Ken Controller

Terminal 1:

```bash
cd ~/Downloads/CCH_Network
./sdn_mpls_demo/run_controller.sh
```

Kiem tra controller:

```bash
sudo ss -ltnp | grep :6653
tail -n 80 sdn_mpls_demo/runtime/controller.log
```

## 5. Chay Mininet topology

Terminal 2:

```bash
cd ~/Downloads/CCH_Network
sudo ./sdn_mpls_demo/run_topology.sh
```

Khi vao prompt:

```text
mininet>
```

## 6. Chay backend

Terminal 3:

```bash
cd ~/Downloads/CCH_Network
./scripts/start_demo.sh --install
```

Script se in `IT operator token`. Nhap token nay vao o `IT token` tren dashboard.

Neu da cai dependency roi:

```bash
./scripts/start_demo.sh
```

Backend:

```text
http://127.0.0.1:8000
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## 7. Chay frontend

Neu dung `scripts/start_demo.sh`, frontend da duoc chay tai:

```text
http://127.0.0.1:5173
```

Mo tu Windows host:

```bash
hostname -I
```

Sau do mo:

```text
http://<IP_VM>:5173
```

## 8. Chay testpolicy trong Mininet

Tai Terminal 2, trong prompt `mininet>`:

```text
testpolicy
```

Ket qua mong doi: tat ca policy test PASS. Neu FAIL, luu log controller va dump flow.

## 9. Dump OpenFlow flow

Trong terminal Ubuntu:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows core_hq
sudo ovs-ofctl -O OpenFlow13 dump-flows dist_branch
sudo ovs-ofctl -O OpenFlow13 dump-flows access_hq_a
sudo ovs-ofctl -O OpenFlow13 dump-flows access_branch
```

Luu output vao file:

```bash
mkdir -p artifacts/review
sudo ovs-ofctl -O OpenFlow13 dump-flows core_hq > artifacts/review/core_hq_flows.txt
sudo ovs-ofctl -O OpenFlow13 dump-flows dist_branch > artifacts/review/dist_branch_flows.txt
```

## 10. Test Ping ALLOW

Trong `mininet>`:

```text
h20_01 ping -c 2 h90
h20_01 ping -c 2 hcall
h50_01 ping -c 2 h90
h50_01 ping -c 2 hcall
h70_01 ping -c 2 h20_01
h70_01 ping -c 2 h50_01
```

Tren dashboard:

- Chon Source/Destination tu combobox.
- Bam Ping.
- Kiem tra ket qua ping that.
- Kiem tra packet animation di dung path backend tra ve.

## 11. Test Ping DENY

Trong `mininet>`:

```text
h20_01 ping -c 2 h30_01
h50_01 ping -c 2 h60_01
h20_01 ping -c 2 hsocial
h50_01 ping -c 2 hsocial
hinternet ping -c 2 h20_01
```

Tren dashboard:

- Ket qua phai DENY.
- Dau X dung enforcement point.
- Project isolation dung `core_hq`.
- Branch isolation dung `dist_branch`.
- Social block HQ dung `core_hq`.
- Social block Branch dung `dist_branch`.

## 12. Test policy reload

Tren dashboard:

1. Nhap IT token.
2. Vao tab `Chinh sach & OpenFlow`.
3. Tat `Chan Social Media`.
4. Kiem tra controller reload thanh cong.
5. Ping `h20_01 -> hsocial` va ghi nhan thay doi.
6. Bat lai `Chan Social Media`.
7. Kiem tra flow DROP duoc cai lai.

Log can xem:

```bash
tail -n 120 sdn_mpls_demo/runtime/controller.log
cat sdn_mpls_demo/runtime/installed_flows.json | head
```

## 13. Test link fail/recover

Tren dashboard:

1. Chon link tren so do.
2. Bam link down.
3. Chay Ping ALLOW di qua link do.
4. Kiem tra ping doi sang fail/deny do failed link.
5. Bam recover.
6. Chay ping lai, kiem tra phuc hoi.

Trong Ubuntu, kiem tra interface:

```bash
ip link show
sudo ovs-vsctl show
```

Trong `mininet>` co the dung:

```text
links
```

## 14. Test realtime metrics

Tren dashboard:

1. Vao tab `Do kiem mang`.
2. Chon source/destination.
3. Bat realtime chart.
4. Kiem tra WebSocket online.
5. Kiem tra delay/loss/jitter/throughput cap nhat theo cap dang chon.

Backend log:

```bash
tail -n 120 logs/backend.log
```

## 15. Test iperf TCP/UDP

Tren dashboard:

- Chon `h20_01 -> hcall`.
- Bam `Throughput TCP`.
- Bam `Jitter UDP`.
- Chon `h50_01 -> hcall`.
- Lap lai TCP/UDP.

Kiem tra:

- Response co `session_id`.
- Port khac nhau theo session.
- Khong kill session iperf khac.
- Ket qua la output that tu Mininet namespace.

## 16. Test voice estimate

Tren dashboard:

```text
h20_01 -> h90
h50_01 -> h90
```

Bam `Uoc luong chat luong thoai`.

Kiem tra:

- MOS/R-factor la uoc luong.
- Khong ghi la SIP/RTP call that.
- Co RTT, jitter, packet loss, throughput.

## 17. Screenshot can tao

Tao thu muc:

```bash
mkdir -p artifacts/review
```

Can luu:

```text
artifacts/review/final-dashboard-overview.png
artifacts/review/final-ping-animation.png
artifacts/review/final-openflow-table.png
artifacts/review/final-realtime-metrics.png
```

## 18. Danh sach log can luu

```bash
mkdir -p artifacts/review/logs
cp sdn_mpls_demo/runtime/controller.log artifacts/review/logs/controller.log
cp logs/backend.log artifacts/review/logs/backend.log
cp logs/frontend.log artifacts/review/logs/frontend.log
cp sdn_mpls_demo/runtime/installed_flows.json artifacts/review/logs/installed_flows.json
sudo ovs-vsctl show > artifacts/review/logs/ovs-vsctl-show.txt
sudo ovs-ofctl -O OpenFlow13 dump-flows core_hq > artifacts/review/logs/core_hq-flows.txt
sudo ovs-ofctl -O OpenFlow13 dump-flows dist_branch > artifacts/review/logs/dist_branch-flows.txt
```

Neu `testpolicy` co output dai, copy terminal output vao:

```text
artifacts/review/logs/testpolicy-output.txt
```

## 19. Dieu kien ket luan PASS

Chi ghi PASS khi da chay that:

- Static tests PASS.
- OS-Ken chay va co port 6653.
- Mininet topology chay.
- `testpolicy` PASS.
- Ping ALLOW/DENY dung policy.
- Dashboard packet animation dung path.
- Link fail/recover thay doi ping that.
- Policy reload thay doi flow/ping that.
- Realtime metrics co du lieu.
- Iperf TCP/UDP co output that.
- Screenshot duoc tao.

Neu chua chay du cac muc tren, trang thai la:

```text
Phase 28: Pending Ubuntu Runtime Validation.
```
