# Phase 47 regression matrix — Full-SDN

> **Legacy / Historical Reference** — Hồ sơ regression theo mốc triển khai; dùng [Testing và acceptance](testing_and_acceptance.md) cho quy trình hiện hành.

| Gate | Command | Runtime/root | PASS condition |
|---|---|---:|---|
| Source/static | `./scripts/phase47_full_regression_gate.sh static` | No | validation, full pytest, docs links và secret scan exit 0 |
| Frontend | `./scripts/phase47_full_regression_gate.sh frontend` | No | lint, Vitest, typecheck và build exit 0 |
| Runtime | `./scripts/phase47_full_regression_gate.sh runtime` | Yes | topology live, đúng 6 OVS, preflight và API health PASS |
| Full | `./scripts/phase47_full_regression_gate.sh full` | Yes | ba gate trên cùng PASS |

Runtime gate không tự khởi động Mininet và không biến thiếu dependency thành PASS. Inventory OVS hiện hành: `access_floor1`, `access_floor2`, `core_hq`, `access_branch`, `dist_branch`, `infra_access`.
