# Full-SDN Enterprise Runtime

Đây là runtime chính của CCH_Network: Mininet + 6 Open vSwitch + OS-Ken OpenFlow 1.3.

## Thành phần

```text
OS-Ken: controller_fabric.py
OVS:    access_floor1, access_floor2, core_hq,
        access_branch, dist_branch, infra_access
WAN:    VLAN 93 L2VPN Primary/Backup Linux bridges
Edge:   nftables firewall namespaces và Internet/Partner simulators
```

CE, L2VPN, firewall và service zone không phải OpenFlow target.

## Pipeline

```text
Table 0  Ingress/VLAN validation
   ↓
Table 10 Protocol classification + Port/VLAN/Subnet IP anti-spoofing
   ↓
Table 20 Security policy + default-deny + dynamic 5-tuple return
   ↓
Table 30 Explicit L2/L3 forwarding + VLAN push/pop
```

Controller không dùng `OFPP_NORMAL`.

## Runtime inventory

- 90 corporate users: Project 1/2/3/4 và IT Support.
- Project 2 dùng VLAN 93 cho 10 user HQ + 10 user Branch.
- Guest VLAN 120, HQ IoT VLAN 140, Branch IoT VLAN 50.
- 7 infrastructure services tại VLAN 100.
- 5 Internet/Partner service simulators.

## Chạy

Terminal 1:

```bash
./sdn_mpls_demo/run_controller.sh
```

Terminal 2:

```bash
sudo ./sdn_mpls_demo/run_topology.sh
```

Terminal 3:

```bash
./scripts/start_demo.sh
```

## Kiểm thử

```bash
python -m pytest -q tests/test_full_sdn_fabric.py
sudo -E sdn_mpls_demo/.venv/bin/python sdn_mpls_demo/run_live_tests.py
```

Suite tương ứng có 24 unit cases và 27 live traffic cases.

## VLAN 93 failover

Primary và Backup là attachment paths riêng. Backup ở standby khi Primary healthy. Fail/recover attachment link Primary làm control agent đổi path active; không tuyên bố carrier protection hoặc hội tụ tức thời.

## Giới hạn

IPv4-only, không static MAC binding, không end-to-end QoS proof, không cryptographic IPsec/provider MPLS control-plane proof và chưa production-ready.

Xem [README chính](../README.md), [thiết kế SDN](../docs/sdn_design.md) và [demo script](../DEMO_SCRIPT.md).
