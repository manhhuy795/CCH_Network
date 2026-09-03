# Xác thực Dashboard runtime trên Ubuntu

## Khởi động

```bash
./sdn_mpls_demo/run_controller.sh
sudo ./sdn_mpls_demo/run_topology.sh
./scripts/start_demo.sh
```

## Static/frontend

```bash
python -m pytest -q
npm run lint --prefix dashboard/frontend
npm run test --prefix dashboard/frontend
npm run typecheck --prefix dashboard/frontend
npm run build --prefix dashboard/frontend
```

## Live

```bash
./scripts/check_demo_health.sh
sudo -E sdn_mpls_demo/.venv/bin/python scripts/mininet_dashboard_preflight.py
sudo -E sdn_mpls_demo/.venv/bin/python sdn_mpls_demo/run_live_tests.py
```

Dashboard phải hiển thị đúng 6 OVS, VLAN 93, 90 corporate users, pipeline `0 → 10 → 20 → 30` và runtime evidence. Routed intersite, performance samples và failover phải được ghi đúng là lab abstraction/measurement, không phải crypto/SLA/carrier guarantee.
