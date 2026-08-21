# SDN MPLS Demo - Call Center BPO

Day la lab mo phong **Hybrid MPLS L3VPN Logic + SDN Edge Policy** cho hai
site vat ly: HQ va Branch Telesale. Lab khong thay the MPLS provider-grade,
MP-BGP, PE/P core hay firewall appliance production.

## Mo hinh dieu khien

OS-Ken dieu khien dung 8 OVS bang OpenFlow 1.3:

```text
access_floor1  access_floor2  dist_hq_1  dist_hq_2
core_hq       infra_access   access_branch  dist_branch
```

CE, firewall va MPLS logic cloud khong phai OpenFlow switch:

```text
ce_hq  ce_telesale  fw_hq  fw_telesale  mpls_primary  mpls_backup
```

`service_net` chi la Linux bridge noi cac service namespace; no khong duoc
tinh vao inventory OVS.

## VLAN va endpoint

- VLAN 20/30/40: Project A/B/C.
- VLAN 50: Telesale tai Branch.
- VLAN 60/70: BackOffice va IT Support tai HQ Floor 2.
- VLAN 90: Voice service.
- VLAN 100: Infrastructure Services.
- VLAN 110: IoT HQ; VLAN 111: IoT Branch.
- VLAN 120: Guest.

Topology co 110 user, 5 service nghiep vu va 9 service ha tang.
Guest/IoT dung reservation hoac DHCP relay theo policy. DHCP runtime trong
lab hien la phan can xac nhan rieng; khong coi IP tinh la DHCP lease.

## Data path

- Traffic noi HQ: access -> distribution -> `core_hq` -> dich vu HQ.
- Traffic Telesale toi HQ: access -> `dist_branch` -> `ce_telesale` ->
  `mpls_primary` (metric 10) hoac `mpls_backup` (metric 100) -> `ce_hq` ->
  `core_hq`.
- Internet local breakout: user -> firewall cua site -> Internet zone.
- Traffic lien site khong di qua firewall Internet.
- Controller chi la control path, khong nam tren duong di packet.

## Policy chinh

- Co lap Project A/B/C tai `core_hq`.
- Co lap Telesale va BackOffice theo chieu nguon tai `dist_branch` va
  `core_hq`.
- Cho phep Voice, Zalo, Call App/CRM va Internet theo policy.
- Chan Social Media, ke ca IT Support.
- Guest chi ra Internet va toi dich vu ha tang duoc cap.
- IoT chi toi DHCP/DNS/NTP va monitoring/NVR duoc cap.
- Default deny cho traffic khong match.

## Chay lab tren Ubuntu

```bash
cd ~/Downloads/CCH_Network
source .venv/bin/activate
python3 scripts/validate_redesigned_topology.py
sudo bash sdn_mpls_demo/run_topology.sh
```

Trong terminal khac:

```bash
cd ~/Downloads/CCH_Network
sudo bash scripts/test_data_flows_runtime.py
sudo bash scripts/test_redesigned_topology_runtime.py
sudo bash scripts/test_mpls_failover_runtime.py
```

## Kiem tra policy va flow

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows core_hq
sudo ovs-ofctl -O OpenFlow13 dump-flows dist_branch
sudo ovs-ofctl -O OpenFlow13 dump-flows access_floor1
sudo ovs-ofctl -O OpenFlow13 dump-flows access_floor2
```

Xem ma tran ping:

```bash
sudo python3 scripts/test_data_flows_runtime.py
```

Xem bao cao trong `runtime_reports/`. Bao cao runtime chi duoc tao khi
Mininet, OVS va control agent thuc su dang chay.

## Don dep

```bash
sudo mn -c
```

Chi ket luan runtime PASS sau khi chay tren Ubuntu co Mininet, Open vSwitch
va OS-Ken. Kiem tra static tren Windows khong phai runtime validation.
