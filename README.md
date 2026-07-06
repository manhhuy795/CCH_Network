# Network Automation - Call Center BPO

Network-as-Code repository for a two-site Call Center BPO topology. It renders
candidate configs, validates inputs, backs up current configs, deploys with a
dry-run default, verifies state, and supports guarded rollback.

Default device templates are Cisco IOS-like for switches/routers. Firewall
output is vendor-neutral first, with an optional FortiGate example template.
An optional SDN intent layer can render controller-neutral policy JSON before
posting to a real controller.

## Safety Rules

- Do not deploy to production before testing in a lab.
- Review vendor syntax before applying generated configs.
- `deploy_configs.py` is dry-run by default.
- Real device connections are blocked unless `CONFIRM_DEPLOY=true`.
- Back up devices before any deploy.
- Zalo and Call App objects are placeholders. Update real FQDN, App-ID, IP and
  ports before production.
- The Voice/Mgmt switch is a double SPOF: failure can remove voice and the
  management path. Use redundant switches and/or OOB management.
- Single CE/uplink is a WAN SPOF. Use redundant CE/uplinks for production.
- This design is MPLS L3VPN. Do not build IPSec tunnels or CE-to-CE static
  routes. ISP-managed MP-BGP inside the MPLS core is out of company scope.
- SDN integration is optional and dry-run by default. It must not program ISP
  MPLS PE/P routers.

## Repository Layout

```text
inventories/             Ansible inventory examples
vars/                    Source-of-truth YAML
templates/               Jinja2 templates
generated_configs/       Rendered candidate configs
backups/                 Timestamped backup configs
playbooks/               Ansible orchestration wrappers
scripts/                 Python automation
tests/                   Unit tests
docs/                    Design notes
sdn_demo/                Mininet/Open vSwitch SDN simulation demo
```

## Install

### Windows

```powershell
cd network-automation-callcenter-bpo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

On Windows, if `python` is not associated correctly, use `py -3` instead, for
example `py -3 scripts/validate_vars.py`.

### Linux VM

You can use a Linux VM for local/offline testing without any network device VM.
For live SSH backup/deploy, add GNS3/EVE-NG/CML nodes or real reachable devices
and update `inventories/lab_inventory.yml`.

Ubuntu/Debian example:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
cd ~/Project/network-automation-callcenter-bpo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```text
NET_USERNAME=netops
NET_PASSWORD=...
NET_SECRET=...
CONFIRM_DEPLOY=false
SDN_CONTROLLER_URL=
SDN_USERNAME=
SDN_PASSWORD=
```

Keep `CONFIRM_DEPLOY=false` while validating and rendering.

## Run Workflow

Validate source-of-truth:

```powershell
python scripts/validate_vars.py
```

Generate candidate configs:

```powershell
python scripts/generate_configs.py
```

Offline verify rendered configs:

```powershell
python scripts/verify_network.py
```

Deploy dry-run:

```powershell
python scripts/deploy_configs.py --generate
```

Render optional SDN intent policy:

```powershell
python scripts/generate_sdn_policies.py
```

## SDN Simulation Demo

The `sdn_demo/` module runs a practical SDN demo in an Ubuntu VM with Mininet,
Open vSwitch and OS-Ken/Ryu. It does not require physical devices.

It simulates:

- HQ Project A/B/C traffic isolation.
- Voice service access when `voice_enabled=true`.
- Zalo and Call App allowed.
- Social Media blocked.
- Branch Telesale and Branch Admin limited by policy.

Quick start on Ubuntu:

```bash
chmod +x sdn_demo/run_demo.sh
chmod +x sdn_demo/setup_ubuntu_vm_vi.sh
./sdn_demo/setup_ubuntu_vm_vi.sh
./sdn_demo/run_demo.sh
```

Inside Mininet, copy/paste command lines from `sdn_demo/test_commands.txt`:

```text
h20 ping -c 2 h30
h20 ping -c 2 h90
h20 ping -c 2 hzalo
h20 ping -c 2 hcall
h20 ping -c 2 hsocial
h50 ping -c 2 h60
h50 ping -c 2 hcall
h50 ping -c 2 hsocial
```

See `sdn_demo/README.md` and `docs/sdn_mininet_demo.md`.

Backup dry-run:

```powershell
python scripts/backup_configs.py --dry-run
```

Real backup after lab testing and change approval:

```powershell
$env:CONFIRM_DEPLOY="true"
python scripts/backup_configs.py --inventory inventories/lab_inventory.yml
```

Real deploy:

```powershell
$env:CONFIRM_DEPLOY="true"
python scripts/deploy_configs.py --inventory inventories/lab_inventory.yml --apply
```

Live verify:

```powershell
$env:CONFIRM_DEPLOY="true"
python scripts/verify_network.py --live --inventory inventories/lab_inventory.yml
```

Rollback dry-run:

```powershell
python scripts/rollback.py --device hq-core-l3 --backup-file backups\hq-core-l3_running_YYYYMMDD-HHMMSS.cfg
```

Rollback apply requires `CONFIRM_DEPLOY=true` and an interactive confirmation:

```powershell
$env:CONFIRM_DEPLOY="true"
python scripts/rollback.py --device hq-core-l3 --backup-file backups\hq-core-l3_running_YYYYMMDD-HHMMSS.cfg --apply
```

## Ansible Wrappers

```powershell
ansible-playbook playbooks/01_precheck.yml
ansible-playbook playbooks/03_generate_configs.yml
ansible-playbook playbooks/04_deploy.yml
ansible-playbook playbooks/05_verify.yml
ansible-playbook playbooks/07_sdn_policy.yml
```

Real deploy via playbook:

```powershell
$env:CONFIRM_DEPLOY="true"
ansible-playbook playbooks/04_deploy.yml -e deploy_apply=true
```

Real SDN apply requires controller URL, credentials if needed, and
`CONFIRM_DEPLOY=true`:

```powershell
$env:CONFIRM_DEPLOY="true"
$env:SDN_CONTROLLER_URL="https://controller.example.com"
python scripts/generate_sdn_policies.py --apply
```

## Tests

```powershell
pytest
```

Tests prove:

- VLAN schema and gateway validation works.
- HQ VLAN 20/30/40 ACL isolation exists.
- Branch VLAN 50/60 have separate policy.
- Rendered configs include expected ACL and route statements.
- CE routers do not route directly to remote CE IPs.
- SDN intents reference known VLANs/devices and render valid JSON.

## Design Scope

Only CE routers connect to the MPLS cloud. CE static routes point to local ISP PE
IP addresses. There are no IPSec tunnels and no direct CE-to-CE static next-hops.

See:

- `docs/topology.md`
- `docs/routing_design.md`
- `docs/acl_design.md`
- `docs/firewall_policy.md`
- `docs/sdn_design.md`
- `docs/gns3_lab.md`
- `docs/sdn_mininet_demo.md`
