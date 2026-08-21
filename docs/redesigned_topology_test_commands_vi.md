# Lenh test topology redesign

## Static tren Windows hoac Ubuntu

```bash
python scripts/validate_vars.py
python scripts/generate_configs.py
python scripts/verify_network.py
python scripts/validate_redesigned_topology.py
pytest -q tests/test_three_layer_topology.py tests/test_floor_group_mapping.py \
  tests/test_branch_telesale_iot_only.py tests/test_dhcp_relay_contract.py \
  tests/test_ups_monitoring_contract.py tests/test_mpls_primary_backup.py \
  tests/test_data_flow_contract.py tests/test_topology_api_contract.py \
  tests/test_topology_ui_contract.py tests/test_policy_enforcement_mapping.py
```

`validate_redesigned_topology.py` chi PASS khi source-of-truth va policy that
khop. Khong can Mininet cho static gate.

## Runtime Ubuntu

Sau khi topology, OS-Ken va control agent dang chay:

```bash
sudo -E .venv/bin/python scripts/test_redesigned_topology_runtime.py
sudo -E .venv/bin/python scripts/test_data_flows_runtime.py
sudo -E .venv/bin/python scripts/test_ups_monitoring_runtime.py
sudo -E .venv/bin/python scripts/test_mpls_failover_runtime.py
sudo -E .venv/bin/python scripts/test_dhcp_runtime.py
```

Runtime script khong fake PASS. DHCP se tra exit code 2/PENDING neu chua co
DHCP daemon va lease record live. `scripts/phase_topology_redesign_acceptance.sh`
chay static gate truoc; tren Windows no chi bao LIVE_RUNTIME_PENDING.

## Mininet CLI

```text
testpolicy
h20_01 ping -c 2 h30_01
guest_01 ping -c 2 hinternet
guest_01 ping -c 2 h20_01
iot_cam_01 ping -c 2 hnvr
iot_branch_cam_01 ping -c 2 hmonitor
h50_01 ping -c 2 h90
h50_01 ping -c 2 hdialer
h20_01 ping -c 2 hsocial
sh ovs-ofctl -O OpenFlow13 dump-flows core_hq
sh ovs-ofctl -O OpenFlow13 dump-flows dist_branch
```

Expected: Guest Internet, IoT monitoring/NVR, Telesale Voice/CRM PASS; Guest
to Project, Project to Social va Project isolation FAIL/DENY theo policy.
