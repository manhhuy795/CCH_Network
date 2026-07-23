# Phase 48 acceptance checklist

## Git/source
- [ ] Branch đúng feature/phase48-final-ubuntu-acceptance.
- [ ] Working tree sạch trước gate.
- [ ] Phase 44/45, 46, 47 có commit và report xác minh.
- [ ] Không có runtime report, token, socket, PID hoặc node_modules được track.

## Environment
- [ ] Ubuntu/Linux.
- [ ] Python/pytest, Bash, curl, ss, npm.
- [ ] Quyền sudo không tương tác cho OVS/namespace khi cần.
- [ ] Mininet chạy bằng Python hệ thống.
- [ ] OS-Ken controller sẵn sàng tại 6653.

## Static/source of truth
- [ ] validate_vars.py.
- [ ] verify_network.py.
- [ ] pytest đầy đủ.
- [ ] Python compile và Bash syntax.
- [ ] Không overlap/duplicate trong network source of truth.

## Frontend
- [ ] npm test.
- [ ] typecheck.
- [ ] production build.
- [ ] không thay đổi lockfile ngoài ý muốn.

## Runtime inventory
- [ ] Controller 6653, backend 8000, frontend 5173.
- [ ] 110 user và 5 service.
- [ ] 12 OVS và 2 firewall namespace.
- [ ] Control Agent HEALTH thật.
- [ ] flow inventory đọc từ OVS sống.

## SDN/policy/firewall
- [ ] Ping ALLOW h30_01 -> h90.
- [ ] Ping DENY h20_01 -> h30_01.
- [ ] Cookie, priority, switch, match/action xác minh được.
- [ ] Firewall counter thay đổi theo traffic phù hợp.
- [ ] Internet inbound bị chặn đúng policy.

## Traffic/resilience
- [ ] Phase44/45 combined acceptance.
- [ ] dashboard runtime smoke.
- [ ] Phase47 runtime regression.
- [ ] link fail/recover.
- [ ] không có BrokenPipe, unhandled task hoặc port collision.
- [ ] Không còn iperf process treo sau test.

## Hygiene/clean clone
- [ ] failure bundle đã redact.
- [ ] manifest SHA-256 được tạo.
- [ ] clean clone từ GitHub branch.
- [ ] clean clone chạy validate, Phase48 tests và frontend build.
