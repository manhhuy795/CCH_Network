# Nghiệm thu Dashboard runtime trên Ubuntu

Không dùng mock, Windows-only static result hoặc stale report để kết luận live PASS.

## Checklist

- [ ] Controller, topology, backend và frontend đang chạy.
- [ ] API health trả component status thật.
- [ ] Topology canvas hiển thị HQ/Branch/Infra/Firewall/Internet và 6 OVS.
- [ ] VLAN 93 Primary/Backup có status và fail/recover control đúng.
- [ ] Flow view thể hiện Table 0/10/20/30 và zero `OFPP_NORMAL`.
- [ ] Policy/evidence phản ánh same-project, cross-project, Guest/IoT/IT.
- [ ] Unit suite 24/24 PASS.
- [ ] Live traffic suite 27/27 PASS.
- [ ] UI không tuyên bố cryptographic IPsec, production SLA/QoS hoặc hội tụ tức thời.

Lệnh demo canonical: [DEMO_SCRIPT.md](../DEMO_SCRIPT.md).
