# Phase 48 expected results

| Nhóm | Kết quả mong đợi |
|---|---|
| Preflight | Linux, branch đúng, working tree sạch, dependency/source hiện diện |
| Static | validation, pytest, Bash syntax, frontend test/typecheck/build đều exit 0 |
| Runtime | controller/backend/frontend/listening; topology, OVS, firewall, agent và flow sống |
| Policy | h30_01 -> h90 ALLOW; h20_01 -> h30_01 DENY với policy contract rõ |
| Resilience | link fail/recover đúng, không làm backend chết, không còn process iperf |
| Clean clone | clone đúng branch, test Phase 48, validate và frontend build thành công |
| Failure | exit khác 0; lưu first failure, log, case result, summary và bundle không chứa secret |

Một report PASS phải có summary.json, case_results.json, manifest.sha256, NEXT_ACTION.md và các thư mục artifact. Kết quả runtime chỉ có giá trị tại thời điểm report, không thay thế nghiệm thu thiết bị thật.
