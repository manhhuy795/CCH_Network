# Routing Design

## HQ Core

- Default route points to HQ firewall inside IP `10.10.254.2`.
- Branch prefixes `172.16.50.0/24` and `172.16.60.0/24` point to HQ CE LAN IP
  `10.10.255.2`.

## Branch Distribution

- Default route points to Branch firewall inside IP `10.20.254.2`.
- HQ summarized route `172.16.0.0/16` points to Branch CE LAN IP
  `10.20.255.2`.

## CE Routers

- HQ CE internal VLAN routes point back to HQ Core `10.10.255.1`.
- HQ CE branch MPLS routes point only to local ISP PE `203.0.113.1`.
- Branch CE internal VLAN routes point back to Distribution `10.20.255.1`.
- Branch CE HQ MPLS route points only to local ISP PE `198.51.100.1`.

The CE routers never use the remote CE LAN/WAN IP as a static route next-hop.
