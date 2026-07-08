# SDN Live Web Dashboard

Dashboard nay dung FastAPI de thao tac truc tiep voi Mininet + Open vSwitch.
Ket qua ping, iperf, flow va counter duoc lay tu lab dang chay, khong doc ket qua gia tu file JSON.

## Cach chay nhanh tren Ubuntu VM

Terminal 1: chay SDN lab Mininet:

```bash
cd ~/Downloads/CCH_Network
sudo mn -c
./sdn_demo/run_demo.sh
```

Terminal 2: chay web dashboard:

```bash
cd ~/Downloads/CCH_Network
chmod +x dashboard/run_live_dashboard.sh
./dashboard/run_live_dashboard.sh
```

Mo trinh duyet:

```text
http://127.0.0.1:8000
```

Neu mo tu Windows host vao Ubuntu VM, dung IP cua VM:

```text
http://<ubuntu-vm-ip>:8000
```

## Backend API

```bash
cd dashboard/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo -E .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

API chinh:

```text
GET  /
GET  /live
GET  /api/topology
GET  /api/policies
GET  /api/flows
GET  /api/metrics/current
GET  /api/live/status
POST /api/test/ping
POST /api/test/iperf
POST /api/live/block
POST /api/live/unblock
WS   /ws/metrics
```

## Cac nut tren web

- Ping that: chay `ping` trong namespace Mininet cua source host.
- Do bandwidth TCP/UDP: start `iperf` server tren destination va client tren source.
- Xem flow OVS: chay `ovs-ofctl -O OpenFlow13 dump-flows s1`.
- Block bang OpenFlow: them drop flow priority 500.
- Unblock: xoa drop flow tam thoi.
- So do mang SDN: ve h20/h30/h40/h50/h60, switch s1 va cac service h90/hzalo/hcall/hsocial bang duong thang/ngang/cheo.
- Gia lap goi tin: khi bam Ping, duong di se chuyen xanh neu pass hoac do/dau X neu fail, kem ly do policy.
- Bang OpenFlow da dich: hien y nghia rule, match host, action allow/drop, priority va counter packet/byte.

Neu web bao khong tim thay namespace host, hay kiem tra terminal Mininet van dang o prompt `mininet>`.
