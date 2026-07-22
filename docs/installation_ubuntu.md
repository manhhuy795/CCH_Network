# C?i ??t Ubuntu

## Dependency h? th?ng

Khuy?n ngh? Ubuntu 22.04 ho?c 24.04 ?? c? Python t??ng th?ch project.

~~~bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip mininet openvswitch-switch iperf3 nftables curl nodejs npm
~~~

Kh?ng thay Python h? th?ng. M?i th?nh ph?n d?ng virtualenv ri?ng theo script setup hi?n c?.

## Clone v? chu?n b?

~~~bash
git clone https://github.com/manhhuy795/CCH_Network.git
cd CCH_Network
chmod +x scripts/*.sh sdn_mpls_demo/*.sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
~~~

Chu?n b? OS-Ken theo sdn_mpls_demo/setup_ubuntu_24_04.sh v? backend theo dashboard/backend/requirements.txt. Frontend d?ng package-lock.json:

~~~bash
cd dashboard/frontend
npm ci
npm run build
cd ../..
~~~

## Ki?m tra c?i ??t

~~~bash
.venv/bin/python scripts/validate_vars.py
.venv/bin/python scripts/verify_network.py
bash scripts/phase46_automation_docs_gate.sh preflight --reuse-running
~~~

N?u ch?a c? runtime, preflight ph?i b?o BLOCKED cho th?nh ph?n thi?u; kh?ng coi ?? l? PASS.
