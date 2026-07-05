# SDN Design

This repository includes an optional SDN intent layer. It does not replace the
existing VLAN, ACL, routing, CE, MPLS, or firewall design.

## Scope

The SDN layer is intended for an enterprise LAN fabric or lab controller such as
OpenDaylight, ONOS, Cisco Catalyst Center/DNAC-style intent APIs, or a custom
controller API.

In scope:

- VLAN/group segmentation intent.
- Project isolation intent for VLAN 20/30/40.
- Branch segmentation intent for VLAN 50/60.
- Service insertion intent that keeps internet policy anchored on the firewall.
- Offline rendering to `generated_configs/sdn_intents.json`.

Out of scope:

- Programming ISP MPLS PE/P routers.
- Replacing ISP MP-BGP.
- Creating IPSec/GRE tunnels.
- Static CE-to-CE routing.

## Safety Model

`scripts/generate_sdn_policies.py` renders JSON locally by default. It only posts
to a controller when all of these are true:

- `--apply` is used.
- `CONFIRM_DEPLOY=true` is set.
- `SDN_CONTROLLER_URL` is set.

The default controller type is `generic_rest`; adapt `vars/sdn.yml` and the API
path to your actual SDN platform.

## Commands

Render SDN intent policy:

```bash
python scripts/generate_sdn_policies.py
```

Apply to a controller only after lab testing:

```bash
export CONFIRM_DEPLOY=true
export SDN_CONTROLLER_URL="https://controller.example.com"
export SDN_USERNAME="admin"
export SDN_PASSWORD="secret"
python scripts/generate_sdn_policies.py --apply
```
