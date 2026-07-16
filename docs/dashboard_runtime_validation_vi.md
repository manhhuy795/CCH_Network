# Xac thuc Dashboard Runtime tren Ubuntu

Tai lieu nay danh cho lab Ubuntu co Mininet, Open vSwitch, OS-Ken, FastAPI va
React dashboard dang chay that.

## Static test va live runtime test

Static test chay duoc tren Windows hoac Ubuntu:

```bash
python -m pytest -q
python -m py_compile \
  sdn_mpls_demo/topology_hybrid_sdn.py \
  dashboard/backend/app/mininet_control.py \
  dashboard/backend/app/live_mininet.py
bash -n scripts/*.sh
```

Static test kiem tra contract, parsing, timeout, cleanup va API error mapping.
Static test khong chung minh namespace Mininet, OVS flow hay iperf runtime dang
hoat dong tren Ubuntu.

Live smoke suite goi API that, ping that trong namespace va iperf3 TCP/UDP that.

## Chuan bi hai terminal

Terminal 1:

```bash
cd ~/Downloads/CCH_Network
git pull
chmod +x sdn_mpls_demo/*.sh scripts/*.sh
sudo mn -c
sudo CCH_AUTO_TEST_POLICY=0 ./sdn_mpls_demo/run_topology.sh
```

Giu terminal nay tai prompt `mininet>`.

Terminal 2:

```bash
cd ~/Downloads/CCH_Network
./scripts/stop_demo.sh
./scripts/start_demo.sh --install
./scripts/check_demo_health.sh
```

Khong chay `run_topology.sh` lan thu hai.

## Chay live smoke suite

Trong Terminal 2:

```bash
cd ~/Downloads/CCH_Network
sudo ./scripts/dashboard_runtime_smoke_test.sh
```

Can dung `sudo` vi suite phai kiem tra namespace Mininet, bridge OVS va
OpenFlow flow that. Script doc token tu `logs/operator.token` nhung khong in
gia tri token vao terminal hay artifact.

Suite kiem tra:

- controller `6653`, backend `8000`, frontend `5173`;
- process topology Mininet;
- Control Agent HEALTH;
- bridge `core_hq`, `dist_branch` va OpenFlow flows;
- Ping ALLOW `h30_01 -> h90`;
- Ping DENY `h20_01 -> h30_01`;
- UDP hai lan lien tiep, TCP va Voice Quality;
- Ping va Agent HEALTH sau iperf;
- hai iperf khac destination chay dong thoi;
- hai iperf cung destination, request thu hai phai tra `IPERF_BUSY`;
- log moi khong co BrokenPipe, thread crash, address conflict hay task exception.

## Artifact

Moi lan chay tao:

```text
runtime_reports/dashboard_runtime_<timestamp>.log
runtime_reports/dashboard_runtime_<timestamp>.json
```

Moi case co `PASS/FAIL`, thoi gian chay, `error_code` va response summary.
Script tra exit code `0` khi tat ca case PASS, nguoc lai tra exit code khac `0`.

## Khi co FAIL

Thu thap them:

```bash
tail -n 120 logs/backend.log
tail -n 120 logs/frontend.log
tail -n 120 logs/controller.log
tail -n 120 sdn_mpls_demo/runtime/controller.log
tail -n 120 sdn_mpls_demo/runtime/mininet_control_agent.log
sudo ovs-ofctl -O OpenFlow13 dump-flows core_hq
sudo ovs-ofctl -O OpenFlow13 dump-flows dist_branch
```

Khong danh dau live runtime PASS chi dua tren pytest hoac mock.
