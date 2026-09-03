# SDN Mininet demo hiện hành

Runtime chính nằm trong `sdn_mpls_demo/` và dùng:

- 6 Open vSwitch;
- OS-Ken + OpenFlow 1.3;
- pipeline `Table 0 → 10 → 20 → 30`;
- explicit L2/L3 forwarding, không `OFPP_NORMAL`;
- Full-SDN segmentation, DHCP relay và VLAN 93 attachment-link failover.

Khởi động:

```bash
./sdn_mpls_demo/run_controller.sh
sudo ./sdn_mpls_demo/run_topology.sh
```

Xem [README](../README.md) và [demo script](../DEMO_SCRIPT.md).
