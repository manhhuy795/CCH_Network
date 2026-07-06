# SDN Demo - Mininet + Open vSwitch + OS-Ken/Ryu

This demo runs a practical SDN simulation for the Call Center BPO topology on an
Ubuntu VM. It does not require physical switches, routers or firewalls.

The controller enforces policy with OpenFlow 1.3 rules on Open vSwitch:

- HQ Project A/B/C isolation.
- Voice access when `voice_enabled=true`.
- Zalo and Call App allowed.
- Social Media blocked.
- Branch Telesale and Branch Admin are not fully open to each other.

This is an SDN policy simulation. It does not simulate MPLS L3VPN, does not
create CE-to-CE logic, and does not program ISP MPLS PE/P routers.

## Topology

One central OVS switch is used so the demo runs smoothly on a small VM:

```text
h20      Project A              172.10.20.10/24
h30      Project B              172.10.30.10/24
h40      Project C              172.10.40.10/24
h50      Telesale               172.10.50.10/24
h60      Branch Admin           172.10.60.10/24
h90      Voice service          172.10.90.10/24
hzalo    Zalo simulator         172.10.200.10/24
hcall    Call App simulator     172.10.201.10/24
hsocial  Social Media simulator 172.10.202.10/24
```

Because hosts are in different `/24` networks, the topology installs a fake
gateway ARP entry on each host. The controller then rewrites destination MACs and
outputs packets to the correct OVS port.

## Install Ubuntu Packages

Fast setup script with Vietnamese guidance:

```bash
chmod +x sdn_demo/setup_ubuntu_vm_vi.sh
./sdn_demo/setup_ubuntu_vm_vi.sh
```

Install and run the demo immediately:

```bash
./sdn_demo/setup_ubuntu_vm_vi.sh --run
```

Manual install:

```bash
sudo apt update
sudo apt install -y git python3 python3-pip python3-venv python3-yaml mininet openvswitch-switch
sudo systemctl enable --now openvswitch-switch
```

## Install Controller Dependencies

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r sdn_demo/requirements.txt
```

If OS-Ken is unavailable for your Python version, install Ryu instead:

```bash
pip install ryu PyYAML
```

If both installers fail on a very new Python version such as Python 3.14, use an
Ubuntu LTS VM such as 22.04 or 24.04, or try the apt-packaged Ryu controller:

```bash
sudo apt install -y python3-ryu
```

## Run Controller and Topology Manually

Terminal 1:

```bash
source .venv/bin/activate
osken-manager sdn_demo/controller_callcenter_policy.py --ofp-tcp-listen-port 6653
```

If using Ryu:

```bash
source .venv/bin/activate
ryu-manager sdn_demo/controller_callcenter_policy.py --ofp-tcp-listen-port 6653
```

Terminal 2:

```bash
source .venv/bin/activate
sudo python3 sdn_demo/topology_callcenter.py
```

## Run with Helper Script

```bash
chmod +x sdn_demo/run_demo.sh
./sdn_demo/run_demo.sh
```

The script starts the controller in the background, starts Mininet, and writes
controller logs to:

```text
sdn_demo/controller.log
```

If the script reports that the controller crashed or port `6653` is not
listening, inspect the log:

```bash
cat sdn_demo/controller.log
```

## Test Commands

Inside the Mininet CLI:

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

The same commands, with expected results as comments, are stored in
`sdn_demo/test_commands.txt`. Copy/paste the command part into the Mininet CLI.

Expected results:

```text
h20 -> h30      fail
h20 -> h90      pass
h20 -> hzalo    pass
h20 -> hcall    pass
h20 -> hsocial  fail
h50 -> h60      fail/limited
h50 -> hcall    pass
h50 -> hsocial  fail
```

## Controller Logs

The controller logs each decision:

```text
ALLOW policy: h20(172.10.20.10) -> h90(172.10.90.10)
DENY policy: h20(172.10.20.10) -> h30(172.10.30.10)
DENY default: ...
```

## Cleanup

```bash
sudo mn -c
```

## Files

```text
policy.yml                         Source-of-truth for SDN demo policy
topology_callcenter.py             Mininet/OVS topology
controller_callcenter_policy.py    OS-Ken/Ryu OpenFlow 1.3 controller
run_demo.sh                        Helper runner
test_commands.txt                  Mininet CLI test commands
setup_ubuntu_vm_vi.sh              Vietnamese setup helper for Ubuntu VM
```
