# ACL Design

## HQ Project Isolation

Inbound ACLs are applied to SVI VLAN 20, 30 and 40.

- VLAN 20 denies VLAN 30 and VLAN 40.
- VLAN 30 denies VLAN 20 and VLAN 40.
- VLAN 40 denies VLAN 20 and VLAN 30.
- Each project VLAN can reach Voice VLAN 90 when needed.
- Project VLANs are denied to Management VLAN 10 by default.
- Remaining traffic is permitted so internet traffic can continue to the
  firewall default path.

## Management VLAN

`admin_allowed_sources` in `vars/acl_policies.yml` is the placeholder for
admin/jump hosts. Update it with real NMS, jump server, and admin workstation
sources before production.

## Branch VLANs

VLAN 50 and VLAN 60 have separate policy objects. Full two-way access is not
opened by default. Explicit application/service permits should be added after
real service IPs and ports are known.
