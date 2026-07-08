# SDN Mininet Demo

The `sdn_demo/` module demonstrates the Call Center BPO policy model with
Mininet, Open vSwitch and a standalone Python OpenFlow controller. It is
designed for an Ubuntu VM and does not require physical network devices,
Ryu or OS-Ken.

## What It Proves

- SDN controller can allow or deny traffic based on source/destination IP.
- HQ Project VLAN policy can be simulated:
  - Project A cannot reach Project B/C.
  - Project B cannot reach Project A/C.
  - Project C cannot reach Project A/B.
- Voice service can be allowed through `voice_enabled=true`.
- Zalo and Call App simulators can be allowed.
- Social Media simulator can be blocked.
- Branch Telesale and Branch Admin are not fully open to each other.

## What It Does Not Prove

- It does not simulate MPLS L3VPN.
- It does not create IPSec/GRE tunnels.
- It does not create CE-to-CE routing.
- It does not program ISP MPLS PE/P routers.
- It does not replace Cisco IOS/FortiGate syntax validation.

## Run

Quick Vietnamese setup script:

```bash
chmod +x sdn_demo/setup_ubuntu_vm_vi.sh
./sdn_demo/setup_ubuntu_vm_vi.sh
```

Install and start the demo immediately:

```bash
./sdn_demo/setup_ubuntu_vm_vi.sh --run
```

Manual setup:

```bash
sudo apt update
sudo apt install -y git python3 python3-pip python3-yaml iperf mininet openvswitch-switch
sudo systemctl enable --now openvswitch-switch

chmod +x sdn_demo/run_demo.sh
./sdn_demo/run_demo.sh
```

Inside Mininet, copy/paste the command part from `sdn_demo/test_commands.txt`:

```text
testsdn
sdninfo
sdnstats
sdnbw h20 h90 5
h20 ping -c 2 h30
h20 ping -c 2 h90
h20 ping -c 2 hzalo
h20 ping -c 2 hcall
h20 ping -c 2 hsocial
h50 ping -c 2 h60
h50 ping -c 2 hcall
h50 ping -c 2 hsocial
```

Cleanup:

```bash
sudo mn -c
```

See `sdn_demo/README.md` for the full walkthrough.
