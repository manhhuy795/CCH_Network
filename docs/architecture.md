# Ki?n tr?c h? th?ng

## Ph?m vi

CCH_Network l? m? h?nh Hybrid MPLS L3VPN Logic Simulation + SDN Edge Policy cho Call Center BPO. ??y l? lab logic ch?y b?ng Mininet, Open vSwitch, OS-Ken, FastAPI v? React; kh?ng ph?i c?u h?nh s?n xu?t.

## C?c l?p

- Network automation: vars, templates, inventories, playbooks, scripts v? generated_configs.
- Data plane lab: Mininet host/namespace, 8 OVS, CE logic, firewall namespace va service simulator.
- Control plane: OS-Ken ?i?u khi?n OpenFlow; controller kh?ng n?m tr?n ???ng ?i c?a g?i.
- Operations plane: FastAPI ki?m tra ping/iperf/health, React hi?n th? topology v? packet path.

## Data path

HQ dung access_floor1/access_floor2 -> dist_hq_1/dist_hq_2 -> core_hq. Branch dung access_branch -> dist_branch. Telesale va IoT Branch di qua CE Telesale -> MPLS Primary/Backup -> CE HQ -> Core. Internet Branch breakout tai fw_telesale; Internet HQ breakout tai fw_hq. Social Media bi chan tai firewall local.

## Source of truth

M? h?nh trong vars/network_model.yml c?ng vars/sites.yml, vars/routing.yml v? vars/firewall_policies.yml l? ngu?n m? t?. scripts/network_model.py ??c, chu?n h?a v? ki?m tra m? h?nh. Topology Mininet v? dashboard kh?ng ???c d?ng d? li?u gi? ?? thay th? runtime evidence.

## Ranh gi?i

MPLS l? transport logic. CE, firewall v? service zone kh?ng ???c coi l? OpenFlow device n?u model kh?ng khai b?o nh? v?y. Flow runtime ch? ???c k?t lu?n t? truy v?n OVS s?ng; file inventory t?nh kh?ng ph?i b?ng ch?ng runtime.
