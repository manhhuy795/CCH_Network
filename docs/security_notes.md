# Ghi chú bảo mật

## Enforcement

- OpenFlow trên 6 OVS thực thi ingress/VLAN validation, Port ↔ VLAN ↔ Subnet IP anti-spoofing, segmentation và default-deny.
- nftables namespaces thực thi firewall boundary cho Internet/Partner và routed intersite traffic.
- Dynamic return flow chỉ mở reverse 5-tuple của phiên hợp lệ và có timeout.
- Không coi `installed_flows.json` là bằng chứng dataplane; phải đọc live flow bằng `ovs-ofctl`.

## Dashboard security

Dashboard dùng server-side session cookie, CSRF và RBAC. Operator token/control-agent token là secret runtime cục bộ:

- không commit;
- không đưa vào URL, screenshot, frontend bundle hoặc report;
- không in bằng `set -x`;
- giới hạn permission file.

API không nhận raw shell command từ client; backend dùng command allowlist/argv cho runtime operations.

## Claim boundary

Lab dùng least-privilege segmentation nhưng không tuyên bố một kiến trúc Zero Trust hoàn chỉnh. Anti-spoofing dựa trên Port/VLAN/Subnet IP, không phải static MAC binding. Voice flow priority không chứng minh queue/DSCP hay end-to-end QoS.

## Giới hạn

- IPv4-only; IPv6 bị drop.
- Attachment-link failover VLAN 93 chỉ là cơ chế lab.
- CE/MPLS/IPsec và firewall HA là abstraction.
- Không dùng kết quả ping/iperf làm bằng chứng production.
- Chưa production-ready; triển khai thật cần hardening, secrets management, change control, backup/rollback, monitoring và failure testing.
