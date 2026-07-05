# Topology

## HQ

- Access Switch A: VLAN 20 Project A users.
- Access Switch B: VLAN 30 Project B users.
- Access Switch C: VLAN 40 Project C users.
- Voice/Mgmt Switch: VLAN 10 management and VLAN 90 voice.
- Core L3 Switch: VLAN/SVI 10, 20, 30, 40, 90; trunk to access switches;
  routed link to HQ CE; routed/default path to HQ firewall.
- HQ CE Router: LAN-side to core; WAN-side to ISP MPLS PE.
- HQ Firewall: internet breakout, NAT and application policy.

## Branch

- Branch Access Switch: VLAN 50 telesale and VLAN 60 admin/backoffice.
- Branch Distribution L3 Switch: SVI gateway for VLAN 50/60; routed link to
  Branch CE; default route to Branch firewall.
- Branch CE Router: LAN-side to distribution; WAN-side to ISP MPLS PE.
- Branch Firewall: internet breakout, NAT and application policy.

## MPLS L3VPN Boundary

Only CE routers attach to the MPLS cloud. ISP PE/P routers and MP-BGP inside the
MPLS provider network are outside company configuration scope.

Do not create site-to-site VPN, IPSec tunnel, GRE tunnel, or static routes that
point from one CE router to the other CE router.
