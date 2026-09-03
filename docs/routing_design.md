# Routing design

## HQ gateway

`hq_l3_gateway` dùng default route qua `fw_hq` tại `10.10.254.2`. Prefix Branch IoT `10.20.50.0/24` cũng đi tới firewall HQ để vào routed intersite abstraction.

## Branch gateway

`telesale_l3_gateway` dùng default route qua `fw_telesale` tại `10.20.254.2`. Các mạng HQ được khai báo đi qua firewall Branch và routed intersite abstraction.

## VLAN 93 exception

VLAN 93 không được route giữa hai site:

- cùng subnet `10.10.93.0/24`;
- gateway `10.10.93.1` chỉ tại HQ;
- Branch không có SVI VLAN 93;
- Ethernet frames đi qua L2VPN Primary hoặc Backup attachment path.

## Transit links

| Link | CIDR |
|---|---|
| HQ gateway ↔ Firewall HQ | `10.10.254.0/30` |
| Firewall HQ ↔ routed abstraction | `10.255.20.0/30` |
| routed abstraction ↔ Firewall Branch | `10.255.20.4/30` |
| Firewall Branch ↔ Branch gateway | `10.20.254.0/30` |
| Firewall HQ ↔ Internet zone | `10.255.10.0/30` |
| Firewall Branch ↔ Internet zone | `10.255.10.4/30` |

`ipsec_l3` chỉ mô phỏng IPv4 routed path; không có IKE/ESP/XFRM encryption.
