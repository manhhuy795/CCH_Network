# Lệnh test topology Full-SDN

## Static

```bash
python scripts/validate_vars.py
python scripts/validate_redesigned_topology.py
python -m pytest -q
```

## Flow inventory

```bash
for sw in access_floor1 access_floor2 core_hq access_branch dist_branch infra_access; do
  sudo ovs-ofctl -O OpenFlow13 dump-flows "$sw"
done
```

## Mininet CLI

```text
h101_01 ping -c 3 10.10.101.12
h101_01 ping -c 3 10.10.103.11
guest_01 ping -c 3 10.250.20.30
guest_01 ping -c 3 10.10.101.11
iot_cam_01 ping -c 3 10.10.100.14
iot_cam_01 ping -c 3 10.250.20.30
h110_01 ping -c 3 10.10.101.11
h101_01 ping -c 3 10.10.110.11
```

Expected: same-project, Guest→Internet, IoT→NMS và IT→managed user PASS; cross-project, Guest→internal, IoT→Internet và unsolicited user→IT DROP.

## Live suites

```bash
sudo -E sdn_mpls_demo/.venv/bin/python scripts/test_mpls_failover_runtime.py
sudo -E sdn_mpls_demo/.venv/bin/python sdn_mpls_demo/run_live_tests.py
```

Thực hiện DHCP DORA theo [DEMO_SCRIPT.md](../DEMO_SCRIPT.md); helper cũ chỉ báo
`PENDING` nên không còn được giữ. Dùng cùng tài liệu đó cho walkthrough bảo vệ.
