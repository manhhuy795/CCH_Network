# Phase 48 final acceptance runbook — Full-SDN

> **Legacy / Historical Reference** — Runbook theo mốc triển khai; dùng [Demo script](../DEMO_SCRIPT.md) và [Testing và acceptance](testing_and_acceptance.md) cho lần chạy hiện hành.

## Chuẩn bị

```bash
cd ~/CCH_Network
sudo mn -c
./sdn_mpls_demo/run_controller.sh
```

Mở terminal khác:

```bash
sudo ./sdn_mpls_demo/run_topology.sh
```

Mở terminal thứ ba:

```bash
./scripts/start_demo.sh
```

## Chạy gates

```bash
./scripts/phase47_full_regression_gate.sh static
./scripts/phase47_full_regression_gate.sh frontend
sudo -E ./scripts/phase47_full_regression_gate.sh runtime
sudo -E sdn_mpls_demo/.venv/bin/python sdn_mpls_demo/run_live_tests.py
```

## Acceptance

Kết luận PASS chỉ khi checklist trong [phase48_acceptance_checklist.md](phase48_acceptance_checklist.md) hoàn tất và evidence cho thấy 24/24 unit, 27/27 live traffic, 6/6 OVS, pipeline bốn bảng, policy và VLAN 93 attachment-link failover đúng.

Không tuyên bố production readiness, cryptographic IPsec, carrier MPLS protection, full Zero Trust, static MAC binding hoặc end-to-end QoS.
