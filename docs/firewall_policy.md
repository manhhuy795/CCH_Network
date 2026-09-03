# Firewall policy

Firewall runtime dùng nftables namespaces `fw_hq` và `fw_telesale` để biểu diễn boundary của từng site. Policy canonical nằm tại `vars/firewall_policies.yml`.

## Mặc định

- family/table: `inet cch_filter`;
- input/forward policy: drop;
- allow established/related;
- drop invalid;
- counter và rate-limited drop log;
- NAT runtime tắt vì service zone dùng routed simulation.

## HQ

- Project 1/2/3/4 và IT Support được truy cập Partner PBX/CRM hoặc General Internet khi policy flag cho phép.
- Social Media bị deny.
- Guest chỉ được General Internet.
- VLAN 93 dùng gateway tại HQ nên traffic Internet/Partner của Project 2 Branch đi L2 về HQ trước khi qua `fw_hq`.

## Branch

Branch firewall sở hữu VLAN 50. Branch IoT chỉ được các infrastructure services đã khai báo qua routed intersite abstraction; không có broad Internet allow.

## Boundary

Một nftables namespace đại diện active firewall HA cluster trong lab. Không tuyên bố appliance HA failover, production NAT, cryptographic IPsec hoặc vendor-specific policy parity.
