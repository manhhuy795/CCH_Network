# Phase 47 Full Regression Matrix

This is the Ubuntu-only acceptance inventory for the CCH Network hybrid MPLS/SDN demo. Existing runners provide live product evidence. A row is PASS only when its real command or its authoritative compound runner exits zero. Mandatory failures are never skipped into PASS.

| Case ID | Layer | Requirement | Precondition | Command/Test | Expected result | Notes |
|---|---|---|---|---|---|---|
| A01 | Git/source | Correct remote | Git repo | git remote get-url origin | CCH_Network remote | |
| A02 | Git/source | Correct Phase 47 branch | Clean checkout | git branch --show-current | feature/phase47-full-regression | |
| A03 | Git/source | Clean worktree | No pending changes | git status --porcelain | Empty | |
| A04 | Git/source | No branch divergence | Fetch origin | rev-parse HEAD and remote | Equal | |
| A05 | Git/source | Phase 44/45 ancestry | origin/main | git merge-base | PASS | |
| A06 | Git/source | Phase 46 ancestry | origin/main | git merge-base | PASS | |
| A07 | Git/source | No tracked runtime artifacts | Git repo | git ls-files | No reports/logs | |
| A08 | Git/source | No tracked secrets | Git repo | secret scan | No match | |
| A09 | Git/source | No whitespace errors | Git repo | git diff --check | PASS | |
| B01 | Source of truth | Variable validation | Python/YAML | scripts/validate_vars.py | PASS | |
| B02 | Source of truth | Network verification | Valid vars | scripts/verify_network.py | PASS | |
| B03 | Source of truth | Deterministic generation | Valid vars | scripts/generate_configs.py | No drift | |
| B04 | Source of truth | Topology source tests | Python | source pytest group | PASS | |
| B05 | Source of truth | Policy source tests | Python | policy pytest group | PASS | |
| C01 | Static | Python syntax | Python | py_compile | PASS | |
| C02 | Static | Shell syntax | Bash | bash -n | PASS | |
| C03 | Static | Test collection | pytest | pytest --collect-only | PASS | |
| C04 | Static | Dashboard tests | pytest | dashboard test group | PASS | |
| C05 | Static | Transport/iperf tests | pytest | transport test group | PASS | |
| C06 | Static | Full Python regression | pytest | pytest -q | PASS | |
| C07 | Static | Phase 46 tests | pytest | phase46 test | PASS | |
| C08 | Static | Diff check | Git | git diff --check | PASS | |
| D01 | Frontend | Dependency install | Node >=18 | npm ci | PASS | |
| D02 | Frontend | Component tests | node_modules | npm run test | PASS | |
| D03 | Frontend | TypeScript | node_modules | npm run typecheck | PASS | |
| D04 | Frontend | Production build | node_modules | npm run build | PASS | |
| D05 | Frontend | Lockfile stable | No dependency change | git diff package-lock | Empty | |
| E01 | Phase 46 | Automation/docs gate | Runtime healthy | phase46 gate all --reuse-running | PASS | |
| F01 | Topology | Controller 6653 | OS-Ken | ss -ltn | Listening | |
| F02 | Topology | Backend 8000 | FastAPI | ss -ltn | Listening | |
| F03 | Topology | Frontend 5173 | Vite | ss -ltn | Listening | |
| F04 | Topology | Topology process | Mininet | pgrep topology | Present | |
| F05 | Topology | Twelve OVS bridges | OVS | ovs-vsctl list-br | Exact twelve | |
| F06 | Topology | Two firewall namespaces | Mininet | ip netns list | fw_hq/fw_telesale | |
| F07 | Topology | Agent health | Socket live | /api/health | agent online | |
| G01 | SDN/OpenFlow | OpenFlow flows on all OVS | Controller | ovs-ofctl dump-flows | actions present | |
| G02 | SDN/OpenFlow | Cookie/priority evidence | core/dist | dump-flows | Present | |
| G03 | SDN/OpenFlow | OpenFlow 1.3 | OVS | ovs-ofctl -O OpenFlow13 | PASS | |
| G04 | SDN/OpenFlow | Live allow ping | Runtime | h30_01 -> h90 | ALLOW | |
| G05 | SDN/OpenFlow | Live deny ping | Policy | h20_01 -> h30_01 | POLICY_DENIED | |
| H01 | Firewall | Runtime counter check | Namespaces | phase44 firewall check | PASS | |
| H02 | Firewall | HQ rules | fw_hq | nft list table | Social rule | |
| H03 | Firewall | Telesale rules | fw_telesale | nft list table | Social rule | |
| H04 | Firewall | Forwarding | Both firewalls | sysctl ip_forward | 1 | |
| I01 | Dashboard/API | Health contract | Backend | GET /api/health | Components | |
| I02 | Dashboard/API | Live status | Backend | GET /api/live/status | Runtime payload | |
| I03 | Dashboard/API | Topology API | Backend | GET /api/topology | PASS | |
| I04 | Dashboard/API | Firewall API | Backend | GET /api/firewalls | PASS | |
| I05 | Dashboard/API | Operator auth | Token file | GET /api/auth/verify | authenticated | |
| J01 | Traffic | Dashboard smoke | Full runtime | dashboard_runtime_smoke_test.py | 21/21 | |
| J02 | Traffic | Ping ALLOW | Mininet | smoke ping | PASS | |
| J03 | Traffic | Ping DENY | Policy | smoke deny | POLICY_DENIED | |
| J04 | Traffic | UDP 5 seconds | iperf3 | smoke UDP | PASS | |
| J05 | Traffic | TCP 5 seconds | iperf3 | smoke TCP | PASS | |
| J06 | Traffic | Voice Quality | Voice path | smoke call-quality | PASS | |
| J07 | Traffic | Different destinations | Runtime | smoke concurrency | PASS | |
| J08 | Traffic | Same destination busy | Runtime | smoke concurrency | HTTP 409 IPERF_BUSY | |
| K01 | Resilience | Link fail | Operator auth | POST link/fail | down | |
| K02 | Resilience | Link recover | Link failed | POST link/recover | up | |
| K03 | Resilience | No iperf orphan | Traffic complete | pgrep iperf3 | Empty | |
| L01 | Process hygiene | One backend | Demo running | pgrep uvicorn | one | |
| L02 | Process hygiene | One frontend | Demo running | pgrep vite | one | |
| L03 | Process hygiene | One controller | OS-Ken | pgrep osken | one | |
| L04 | Process hygiene | No iperf orphan | Traffic complete | pgrep iperf3 | Empty | |
| M01 | Documentation | Matrix exists | Git checkout | test -s matrix | PASS | |
| M02 | Documentation | Gate executable | Git checkout | test -x gate | PASS | |
| M03 | Documentation | Phase 47 test | pytest | test_phase47_full_regression.py | PASS | |
