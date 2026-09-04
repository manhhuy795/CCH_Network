# Testing và acceptance

## Kết quả chuẩn

| Suite | Phạm vi | Kết quả gần nhất |
|---|---|---|
| Full-SDN unit | Pipeline, no `OFPP_NORMAL`, VLAN push/pop, policy, anti-spoofing, DHCP relay, 5-tuple, failover | **24/24 PASS** |
| Live traffic | 6 OVS connection, pipeline, allow/drop, Guest/IoT/IT, anti-spoofing, L3 rewrite, VLAN 93 failover | **27/27 PASS** |
| Repository Python/backend | Unit, API, auth/RBAC, transport, topology/contract | Chạy lại bằng `pytest -q` |
| Frontend | ESLint, Vitest, TypeScript, Vite build | Chạy lại bằng npm gates |

Mốc live 27/27 được ghi nhận trên Ubuntu lab ngày 2026-08-26. Kết quả live không được suy ra từ static tests và chỉ có giá trị cho runtime đã tạo evidence.

## Static/Python

```bash
python -m pytest -q tests/test_full_sdn_fabric.py
python -m pytest -q
python scripts/validate_vars.py
python scripts/validate_topology.py
```

Kỳ vọng file `tests/test_full_sdn_fabric.py` thu đúng 24 cases.

## Backend

```bash
python -m pytest -q \
  tests/test_dashboard_health_api.py \
  tests/test_activity_history.py \
  tests/test_auth_rbac.py \
  tests/test_mininet_control_timeouts.py \
  tests/test_mininet_control_transport.py
```

Các test này dùng mock/contract phù hợp và không kết luận OVS/Mininet đang sống.

## Frontend

```bash
npm ci --prefix dashboard/frontend
npm run lint --prefix dashboard/frontend
npm run test --prefix dashboard/frontend
npm run typecheck --prefix dashboard/frontend
npm run build --prefix dashboard/frontend
```

## Live Ubuntu

Khởi động controller, topology và dashboard trước, sau đó:

```bash
sudo -E sdn_mpls_demo/.venv/bin/python sdn_mpls_demo/run_live_tests.py
```

Runner có đúng 27 traffic cases và kiểm tra thêm failover sequence. PASS yêu cầu:

- 6/6 OVS connected;
- không có `actions=NORMAL`;
- pipeline `0 → 10 → 20 → 30`;
- same-project allow, cross-project drop;
- Guest/IoT/IT policy đúng;
- Port ↔ VLAN ↔ Subnet IP anti-spoofing;
- L3 rewrite/TTL decrement hiện diện;
- VLAN 93 reachable trên Primary, Backup và sau restore.

## GitHub Actions

Workflow `.github/workflows/ci.yml` có ba job:

1. 24 Full-SDN unit cases.
2. Backend và các repository contracts còn lại.
3. Frontend lint/test/typecheck/build.

GitHub-hosted runner không chạy Mininet/OVS/root integration. Live suite phải chạy trên Ubuntu lab hoặc self-hosted runner chuyên dụng.

## Ý nghĩa trạng thái

- **PASS**: case đã chạy và kết quả khớp.
- **FAIL**: case đã chạy nhưng hành vi sai.
- **BLOCKED/NOT RUN**: thiếu runtime/dependency/quyền; không được đổi thành PASS.
