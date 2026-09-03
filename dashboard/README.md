# CCH Full-SDN Dashboard

Dashboard vận hành cho lab Full-SDN gồm FastAPI backend và React/Vite frontend.

## Nội dung hiển thị

- health của OS-Ken, 6 OVS, backend và Mininet control agent;
- enterprise topology HQ/Branch/Infrastructure/Firewall/Internet;
- VLAN 93 L2VPN Primary/Backup và attachment-link fail/recover;
- OpenFlow pipeline `0 → 10 → 20 → 30`, flow inventory và policy decision;
- endpoint/host inventory, event log, test/preflight evidence;
- bandwidth/RTT/loss samples của lab, không gắn nhãn production SLA.

Dashboard không biến design metadata hoặc mock thành runtime PASS.

## Cài đặt

```bash
./scripts/start_demo.sh --install
```

Các lần sau:

```bash
./scripts/start_demo.sh
```

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`

Topology Mininet phải được khởi động riêng bằng `sudo ./sdn_mpls_demo/run_topology.sh`.

## Test frontend

```bash
npm ci --prefix dashboard/frontend
npm run lint --prefix dashboard/frontend
npm run test --prefix dashboard/frontend
npm run typecheck --prefix dashboard/frontend
npm run build --prefix dashboard/frontend
```

## Claim boundary

- IPsec hiển thị là IPv4 routed intersite abstraction, không phải bằng chứng IKE/ESP/XFRM.
- Performance panel là sample từ ping/iperf, không phải QoS/SLA guarantee.
- VLAN 93 resilience là attachment-link failover trong lab.
- Hệ thống chưa production-ready.
