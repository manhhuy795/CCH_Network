# V?n h?nh runtime

## Chu?n b?

Gi? topology ch?y ? m?t terminal v? dashboard ? terminal kh?c. Terminal validation d?ng quy?n root khi ??c namespace Mininet v? OVS.

~~~bash
cd /home/huy/Downloads/CCH_Network
sudo ./sdn_mpls_demo/run_topology.sh
~~~

Terminal dashboard:

~~~bash
./scripts/start_demo.sh
~~~

Terminal gate:

~~~bash
sudo -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1   bash scripts/phase46_automation_docs_gate.sh runtime --reuse-running --verbose
~~~

## C?c mode

- preflight: dependency, port, API health, socket v? reuse.
- static: py_compile, bash -n, pytest, frontend npm ci/build, secret scan v? docs link.
- automation: validation network model, script permissions v? clean clone.
- docs: ki?m tra t?i li?u v? link n?i b?.
- runtime: controller 6653, backend 8000, frontend 5173, 8 OVS, flow, agent, 110 user, 2 firewall namespace va Phase 44/45 regression.
- all: ch?y theo th? t?; mode sau b? BLOCKED n?u mode tr??c l?i.

~~~bash
bash scripts/phase46_automation_docs_gate.sh preflight --reuse-running
bash scripts/phase46_automation_docs_gate.sh static --reuse-running
bash scripts/phase46_automation_docs_gate.sh automation --reuse-running
bash scripts/phase46_automation_docs_gate.sh docs --reuse-running
~~~

--start-missing ch? l? cho ph?p operator y?u c?u kh?i ??ng th?nh ph?n dashboard c?n thi?u. Gate kh?ng t? d?n Mininet v? kh?ng t? kh?i ??ng topology ng?m.

## Artifact

M?i l?n ch?y ghi v?o runtime_reports/phase46_automation_docs_<UTC>/. C?c file ch?nh l? baseline.log, project_inventory.md, automation_inventory.md, documentation_inventory.md, files_changed.txt, static_validation.log, runtime_validation.log, phase44_45_regression.log, summary.json v? NEXT_ACTION.md n?u l?i. Token kh?ng ???c ghi v?o artifact.
