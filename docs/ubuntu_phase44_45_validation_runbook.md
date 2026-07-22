# Ubuntu Phase 44/45 Validation Runbook

## Mục tiêu và giới hạn

Bộ validation này chỉ kiểm thử, thu thập bằng chứng và phân loại lỗi trên Ubuntu. Nó không sửa product source, không tự commit/push/switch branch, không reset/clean/stash/restore repository và không tự dừng topology đang chạy.

Ba file của bộ công cụ:

- `scripts/ubuntu_phase44_45_validation_gate.sh`
- `scripts/ubuntu_phase44_45_failure_bundle.sh`
- `docs/ubuntu_phase44_45_validation_runbook.md`

## Chuẩn bị ba Terminal

### Terminal 1 — Topology/Mininet

Giữ topology đang chạy và giữ Terminal tại dấu nhắc:

```text
mininet>
```

Không đóng Terminal này trong khi validation chạy. Script nhận biết chuỗi wrapper `sudo -> env -> python` là một topology logic, không coi ba PID wrapper là ba topology độc lập.

### Terminal 2 — Backend và Frontend

Giữ Backend cổng `8000` và Frontend cổng `5173` đang chạy. Có thể kiểm tra:

```bash
ss -ltnp | grep -E ':(8000|5173)([[:space:]]|$)'
```

Tùy chọn `--start-dashboard` chỉ dùng official `scripts/start_demo.sh` khi script validation chứng minh được official script có chế độ dashboard-only an toàn. Nó không kill dịch vụ đang chạy và không tự khởi động topology.

### Terminal 3 — Validation

```bash
cd /home/huy/Downloads/CCH_Network

bash scripts/ubuntu_phase44_45_validation_gate.sh preflight --reuse-running

bash scripts/ubuntu_phase44_45_validation_gate.sh static --reuse-running

sudo -v

bash scripts/ubuntu_phase44_45_validation_gate.sh runtime --reuse-running

bash scripts/ubuntu_phase44_45_validation_gate.sh combined --reuse-running
```

Chạy toàn bộ theo gate:

```bash
bash scripts/ubuntu_phase44_45_validation_gate.sh all --reuse-running
```

Ghi report vào đường dẫn riêng:

```bash
bash scripts/ubuntu_phase44_45_validation_gate.sh preflight \
  --reuse-running \
  --report-dir runtime_reports/my_phase44_45_validation
```

## Ý nghĩa các mode

### `preflight`

Thu thập phiên bản Ubuntu, kernel, user, Git, Python virtual environments, Mininet, OVS, OS-Ken, nftables, iperf3, Node/npm; sau đó kiểm tra topology, controller, ba port, chín OVS bridge, namespace firewall, UNIX socket, OpenAPI và backend health.

Preflight cũng kiểm tra source patch từ Windows:

- `scripts/ubuntu_phase44_45_deep_debug.py` tồn tại;
- `tests/test_phase44_git_checkpoint.py` tồn tại;
- test mới được pytest collect;
- deep-debug CLI có `diagnose`, `verify` và ba `run-case` bắt buộc.

Nếu topology chưa chạy, kết quả là `BLOCKED`, không phải `PASS` và script không tự khởi động topology.

### `static`

Chạy theo thứ tự có gate:

1. Python syntax check.
2. `bash -n` cho hai shell script.
3. Pytest collection.
4. Firewall parser tests.
5. Git checkpoint tests.
6. Iperf agent contract tests.
7. Phase 44 firewall tests.
8. Phase 45 dashboard contract tests.
9. Dashboard API tests khi thư mục test tồn tại.
10. Full pytest.
11. `git diff --check`.

Thiếu dependency hoặc Python environment phù hợp sẽ tạo `BLOCKED`/`FAIL` có lý do cụ thể; script không tự cài package và không chạy `sudo pip install`.

### `runtime`

Chạy bằng locale `C.UTF-8`:

```bash
sudo -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 \
  python3 scripts/ubuntu_phase44_45_deep_debug.py diagnose

sudo -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 \
  python3 scripts/ubuntu_phase44_45_deep_debug.py run-case firewall-counter

sudo -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 \
  python3 scripts/ubuntu_phase44_45_deep_debug.py run-case git-checkpoint

sudo -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 \
  python3 scripts/ubuntu_phase44_45_deep_debug.py run-case iperf-concurrency
```

Sau mỗi case, gate xác minh topology/controller/backend còn hoạt động, vẫn có chín OVS bridge và không xuất hiện iperf3 mồ côi mới.

Working tree dirty được phân loại:

```text
VALIDATION_BLOCKED_BY_DIRTY_WORKTREE
COMBINED_ACCEPTANCE_BLOCKED=YES
ACTION_REQUIRED=Create an explicit local checkpoint commit after user approval
```

Validation không tự commit hoặc stash.

### `combined`

Chỉ chạy khi có bằng chứng static PASS, runtime PASS và working tree sạch. Nếu dirty:

```text
COMBINED_STATUS=BLOCKED
REASON=DIRTY_WORKTREE
```

Khi đủ điều kiện, gate chạy official Combined Acceptance rồi đọc `runtime_reports/phase44_45_combined_summary.json`. Exit code bằng 0 nhưng summary thiếu case bắt buộc vẫn bị xem là FAIL.

## PASS, FAIL và BLOCKED

- **PASS**: tất cả case bắt buộc của mode đã chạy và đạt.
- **FAIL**: bằng chứng chỉ ra code, test/acceptance hoặc hành vi runtime sai.
- **BLOCKED**: chưa đủ điều kiện chạy hợp lệ, ví dụ topology/service chưa chạy, repository/venv thiếu hoặc working tree dirty chặn Combined Acceptance.

Không coi một case quan trọng bị skip là PASS.

## Cách đọc report

Mỗi lần chạy tạo:

```text
runtime_reports/ubuntu_phase44_45_validation_<UTC timestamp>/
├── validation.log
├── summary.json
├── cases.jsonl
├── cases/
├── environment/
└── NEXT_ACTION.md          # chỉ có khi FAIL/BLOCKED
```

Trong `summary.json`, xem:

- `overall_status`;
- `first_failure`;
- `failed_cases`;
- `failure_triage.failure_class`;
- `failure_triage.codex_prompt`;
- `failure_triage.ubuntu_script`;
- `failure_triage.next_action_file`;
- `failure_triage.rerun_command`.

## Phân loại lỗi và hành động tiếp theo

### `CODE_ERROR`

Gate tạo `codex_fix_prompt_<case>.md`. Gửi đúng file đó cho Codex. Codex không được commit/push hoặc sửa test để luôn PASS. Sau khi nhận patch, áp dụng trên Ubuntu và chạy lại validation.

### `TEST_OR_ACCEPTANCE_ERROR`

Gate vẫn tạo Codex prompt nhưng ghi rõ vùng sửa là test/acceptance infrastructure. Không sửa product behavior đang đúng chỉ để khớp assertion sai.

### `UBUNTU_ENVIRONMENT_ERROR`

Gate tạo script chẩn đoán Ubuntu an toàn. Chạy:

```bash
bash runtime_reports/.../ubuntu_diagnose_<case>.sh
```

Gửi lại khối `UBUNTU_FIX_SUMMARY` và 200 dòng cuối của `LOG_FILE`.

### `RUNTIME_STATE_ERROR`

Gate tạo `runtime_state_recovery_<case>.sh`. Script ưu tiên chẩn đoán, không phá topology đang hoạt động, không chạy `mn -c` và không tự commit.

### `UNKNOWN`

Gate tạo `ubuntu_collect_more_evidence_<case>.sh`. Chạy script rồi gửi khối:

```text
EVIDENCE_COLLECTION_COMPLETE=YES
UNRESOLVED_QUESTION=...
NEXT_REQUIRED_ARTIFACT=...
```

## Tạo failure bundle

Tạo bundle từ report mới nhất:

```bash
bash scripts/ubuntu_phase44_45_failure_bundle.sh
```

Hoặc chỉ định report:

```bash
bash scripts/ubuntu_phase44_45_failure_bundle.sh \
  --report-dir runtime_reports/ubuntu_phase44_45_validation_<timestamp>
```

Bundle chứa summary/log, failed case stdout/stderr, `NEXT_ACTION.md`, prompt/script triage, Git evidence, package versions, process/port/OVS/namespace/socket evidence và log tail. Bundle loại trừ `logs/operator.token`, nội dung token, credentials và private keys; security scan phải PASS trước khi tạo tarball.

## Khi working tree dirty

Không chạy reset/clean/stash/restore. Xem thay đổi:

```bash
git status --porcelain
git diff --stat
git diff --check
```

Combined Acceptance cần checkpoint Git sạch. Chỉ tạo local checkpoint commit sau khi người dùng xem diff và chấp thuận rõ ràng. Validation không tự thực hiện bước này.

## Dữ liệu cần gửi lại

Khi FAIL/BLOCKED, gửi:

1. `summary.json`;
2. `NEXT_ACTION.md`;
3. stdout/stderr của `first_failure`;
4. artifact Codex prompt hoặc Ubuntu diagnostic script được ghi trong `failure_triage`;
5. failure bundle nếu cần điều tra đầy đủ.

Không chạy lại Combined Acceptance cho đến khi bước xử lý trong `NEXT_ACTION.md` đã báo PASS hoặc điều kiện BLOCKED đã được giải quyết.
