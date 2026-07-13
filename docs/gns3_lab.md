# GNS3 Lab Guide

This guide explains how to test the automation repository with GNS3. Use only
network images that you are licensed or otherwise authorized to use.

## Recommended Lab Images

Use Cisco IOS-like images that support SSH, `show running-config`, interface
configuration, static routes, VLANs and ACLs.

Good fit:

- Cisco IOSv for routers and L3 switch-like tests.
- Cisco IOSvL2 for access switch tests.
- Cisco CSR1000v for router/IOS-XE tests.
- FortiGate VM only if you have a valid image/license.

Avoid using VPCS for Netmiko backup/deploy testing. VPCS is useful for endpoint
ping tests, but it does not support Cisco IOS commands.

## Minimal First Lab

Start with one node before building the full topology:

```text
Linux VM running CCH_Network repo
        |
Management network / cloud / NAT
        |
hq-core-l3 Cisco IOS-like node
```

The first success criteria are:

- Linux VM can ping the node management IP.
- Linux VM can SSH to the node.
- `backup_configs.py --limit hq-core-l3` can collect running/startup config.

## Node Names

Use these names in GNS3 so they match the repository inventory and generated
config names:

```text
hq-core-l3
hq-access-a
hq-access-b
hq-access-c
hq-voice-access
hq-ce-router
br-access
br-dist-l3
br-ce-router
```

Firewall nodes are optional for the first demo because firewall output is
vendor-neutral:

```text
hq-firewall
br-firewall
```

## Suggested Topology

```text
HQ access-a ----+
HQ access-b ----+                       +---- HQ CE ---- ISP/MPLS stub
HQ access-c ----+---- HQ Core L3 -------+
Voice/Mgmt -----+                       +---- HQ Firewall stub

Branch access -------- Branch Dist L3 ---+---- Branch CE ---- ISP/MPLS stub
                                         +---- Branch Firewall stub
```

The ISP/MPLS cloud can be a simple router/stub for lab reachability. Do not
create IPSec or GRE tunnels between CE routers.

## Basic SSH Bootstrap

On each Cisco IOS-like node, configure a reachable management interface and SSH.
Adjust interface names and IPs to your image/topology.

```cisco
conf t
hostname hq-core-l3
username netops privilege 15 secret netops123
enable secret enable123
ip domain-name lab.local
crypto key generate rsa modulus 2048
ip ssh version 2
line vty 0 4
 login local
 transport input ssh
!
interface GigabitEthernet0/0
 description Management to automation VM
 ip address 192.168.56.101 255.255.255.0
 no shutdown
end
write memory
```

Test from the Linux VM:

```bash
ping 192.168.56.101
ssh netops@192.168.56.101
```

## Inventory Mapping

Edit `inventories/lab_inventory.yml` and replace documentation IPs with GNS3
management IPs.

Example:

```yaml
hq-core-l3:
  ansible_host: 192.168.56.101
  ansible_network_os: cisco.ios.ios
  device_role: core_hq
```

## Environment File

```bash
cp .env.example .env
nano .env
```

Example:

```env
NET_USERNAME=netops
NET_PASSWORD=netops123
NET_SECRET=enable123
CONFIRM_DEPLOY=false
```

Keep `CONFIRM_DEPLOY=false` for dry-run and offline checks.

## Test Order

Run offline tests first:

```bash
python scripts/validate_vars.py
python scripts/generate_configs.py
python scripts/verify_network.py
python scripts/generate_sdn_policies.py
pytest
```

Run backup dry-run:

```bash
python scripts/backup_configs.py --dry-run --limit hq-core-l3
```

Allow live backup only after SSH works:

```bash
export CONFIRM_DEPLOY=true
python scripts/backup_configs.py --limit hq-core-l3
```

Deploy dry-run:

```bash
python scripts/deploy_configs.py --generate --limit hq-core-l3
```

Apply to one device only after lab review:

```bash
export CONFIRM_DEPLOY=true
python scripts/deploy_configs.py --apply --limit hq-core-l3
```

## Scaling the Demo

After one node works, add devices in this order:

1. `hq-access-a`
2. `hq-core-l3`
3. `hq-ce-router`
4. `br-dist-l3`
5. `br-ce-router`

Then add the remaining access and optional firewall nodes.

## Endpoint Testing

Use VPCS or lightweight Linux containers as users. You do not need 50 full VMs.
For a demo, create a few endpoints per VLAN and explain that the YAML variables
model approximately 50 users per project/telesale VLAN.

Expected behavior:

- VLAN 20 cannot reach VLAN 30/40.
- VLAN 30 cannot reach VLAN 20/40.
- VLAN 40 cannot reach VLAN 20/30.
- Project VLANs can reach Voice VLAN 90 if required.
- Branch VLAN 50 and VLAN 60 are not fully open to each other.
- CE routers route inter-site prefixes to local ISP PE next-hop only.
