# Phase 7: Security va acceptance

Tai lieu nay la checkpoint cuoi cua dot redesign topology/dataflow. Static
validation da duoc chay tren Windows; live validation Ubuntu khong duoc danh
dau PASS khi SSH toi VM khong ket noi.

## Security contract

- Dashboard dung human session cookie va CSRF double-submit cho browser.
- Operator token chi dung cho backend/runtime script qua
  `X-CCH-Operator-Token`; frontend khong luu token trong localStorage, URL hay
  bundle.
- `viewer` va `auditor` khong duoc chay runtime; `operator` khong co quyen
  quan tri user; `admin` moi duoc quan ly user/role.
- WebSocket phai xac thuc session hoac operator token va tu choi handshake
  bang `4401`/`4403` khi thieu quyen.
- API khong tra traceback cho client; log server giu traceback cung request ID.
- Secret scan bo qua cac mau la bien moi truong/secret runtime va khong in
  dong nguon co the lam lo credential.

## Static evidence tren Windows

Da chay va PASS:

```text
py -3.13 -m pytest -q
py -3.13 scripts/validate_vars.py
py -3.13 scripts/verify_network.py
py -3.13 scripts/phase49_secret_scan.py .
py -3.13 -m compileall -q scripts sdn_mpls_demo dashboard/backend
py -3.13 -m pytest -q tests/test_phase49_auth_rbac.py tests/test_phase46_automation_docs.py tests/test_phase47_full_regression.py
npm run typecheck
npm run test -- --run
npm run build
npm run lint
```

`npm run lint` khong co error; con 2 warning Fast Refresh tai
`RealtimePanel.tsx` do file export them helper status. Day khong phai loi
build/runtime.

## Ubuntu live gate

Trang thai: **PENDING UBUNTU RUNTIME VALIDATION**.

Khong the xac nhan cac hang muc sau cho den khi SSH toi VM hoat dong:

- OS-Ken port 6653 va controller target set;
- topology Mininet va 110 user + 5 service;
- Open vSwitch bridges/flows;
- Mininet Control Agent HEALTH;
- ping ALLOW/DENY, iperf TCP/UDP, voice quality;
- link fail/recover va packet animation tren browser;
- WebSocket handshake, reconnect va realtime metrics;
- firewall counter va policy reload.

Lenh chay tren Ubuntu sau khi SSH hoat dong:

```bash
cd ~/Downloads/CCH_Network
git switch feature/redesign-callcenter-topology-dataflow
git pull --ff-only origin feature/redesign-callcenter-topology-dataflow
./scripts/stop_demo.sh
sudo -n mn -c
./scripts/start_demo.sh
./scripts/check_demo_health.sh
sudo -n bash scripts/phase44_45_combined_acceptance.sh
sudo -n bash scripts/dashboard_runtime_smoke_test.sh
```

Neu script smoke test khong ton tai tren branch, khong thay bang ket qua gia;
ghi `BLOCKED` va chay cac gate Phase 46/48 da co trong repository.

## Ket luan checkpoint

- Phase 3: PASS static, live Ubuntu chua xac nhan trong checkpoint nay.
- Phase 4: PASS static, live OpenFlow chua xac nhan trong checkpoint nay.
- Phase 5: PASS static, live Control Agent chua xac nhan trong checkpoint nay.
- Phase 6: PASS frontend static; packet animation lay decision backend va dung
  tai `blocked_at`.
- Phase 7: static acceptance PASS; Ubuntu runtime PENDING do SSH timeout.

Khong merge vao `main` va khong goi live acceptance la PASS cho den khi co raw
output tu Ubuntu.
