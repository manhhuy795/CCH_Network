# Phase 48 acceptance checklist — Full-SDN

> **Legacy / Historical Reference** — Checklist nghiệm thu theo mốc triển khai; dùng [Testing và acceptance](testing_and_acceptance.md) cho tiêu chí hiện hành.

- [ ] Controller OS-Ken nghe tại `127.0.0.1:6653`.
- [ ] Đúng 6 OVS connected bằng OpenFlow 1.3.
- [ ] Không flow nào dùng `OFPP_NORMAL`.
- [ ] Pipeline `Table 0 → 10 → 20 → 30` hiện diện.
- [ ] Runtime có 90 corporate users và đúng VLAN plan hiện hành.
- [ ] Same-project PASS, cross-project DROP.
- [ ] Guest/IoT/IT least-privilege cases đúng.
- [ ] Port ↔ VLAN ↔ Subnet IP anti-spoofing hiện diện.
- [ ] DHCP DORA/relay có live evidence.
- [ ] VLAN 93 PASS trên Primary, Backup và sau restore.
- [ ] Dashboard health/topology/flow/event dùng runtime data.
- [ ] 24/24 unit và 27/27 live traffic cases PASS.
- [ ] Report ghi rõ IPv4-only, attachment-link failover và chưa production-ready.
