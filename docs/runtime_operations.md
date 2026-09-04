# Vận hành runtime Full-SDN

## Khởi động

Terminal 1:

```bash
cd ~/CCH_Network
./sdn_mpls_demo/run_controller.sh
```

Terminal 2:

```bash
cd ~/CCH_Network
sudo ./sdn_mpls_demo/run_topology.sh
```

Terminal 3:

```bash
cd ~/CCH_Network
./scripts/start_demo.sh
```

`run_topology.sh` có thể tự khởi động controller nếu cổng 6653 chưa có listener, nhưng khi bảo vệ nên chạy controller riêng để quan sát log.

## Health

```bash
sudo ovs-vsctl show
curl -fsS http://127.0.0.1:8000/api/health
./scripts/check_demo_health.sh
```

Inventory đúng gồm 6 OVS: `access_floor1`, `access_floor2`, `core_hq`, `access_branch`, `dist_branch`, `infra_access`.

## Flow inspection

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows core_hq
sudo ovs-ofctl -O OpenFlow13 dump-flows access_floor1 table=0
sudo ovs-ofctl -O OpenFlow13 dump-flows access_floor1 table=10
sudo ovs-ofctl -O OpenFlow13 dump-flows access_floor1 table=20
sudo ovs-ofctl -O OpenFlow13 dump-flows access_floor1 table=30
```

## Gates

```bash
./scripts/run_validation.sh static
./scripts/run_validation.sh frontend
./scripts/run_validation.sh runtime
```

Runtime mode yêu cầu Ubuntu, topology đang chạy và quyền đọc OVS/namespace.

## Log và evidence

- `sdn_mpls_demo/runtime/controller.log`
- `sdn_mpls_demo/runtime/events.jsonl`
- `runtime_reports/`
- `logs/backend.log`
- `logs/frontend.log`

Không commit runtime artifacts, operator token, socket hoặc PID file.

## Dừng

```bash
./scripts/stop_demo.sh
sudo mn -c
```
