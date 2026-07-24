# Testing v? acceptance

## Static

~~~bash
.venv/bin/python -m py_compile scripts/phase46_automation_docs_gate.py
bash -n scripts/phase46_automation_docs_gate.sh
.venv/bin/python -m pytest --collect-only -q
.venv/bin/python -m pytest -q
cd dashboard/frontend
npm ci
npm run build
~~~

Static PASS ch? ch?ng minh source, test v? build h?p l? tr?n m?y ch?y l?nh; kh?ng ch?ng minh Mininet ?ang s?ng.

## Automation/docs

~~~bash
bash scripts/phase46_automation_docs_gate.sh automation --reuse-running
bash scripts/phase46_automation_docs_gate.sh docs --reuse-running
~~~

Automation ki?m tra validate_vars, verify_network, permissions v? clean clone. Docs ki?m tra 6 t?i li?u b?t bu?c v? link n?i b?.

## Live runtime

~~~bash
sudo -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1   bash scripts/phase46_automation_docs_gate.sh runtime --reuse-running --verbose
~~~

Gate phai co bang chung that cho controller, 3 port, 8 OVS, flow OpenFlow 1.3, HEALTH agent, 110 user, 2 firewall namespace, khong co iperf3 mo coi va cac checker Phase 44/45.

## Ph?n lo?i

- PASS: case ?? ch?y v? ??t.
- FAIL: case ?? ch?y nh?ng h?nh vi sai.
- BLOCKED: thi?u ?i?u ki?n, b? skip ho?c kh?ng c? runtime evidence.
- Kh?ng ???c ??i expected, x?a test ho?c bi?n case skip th?nh PASS.
