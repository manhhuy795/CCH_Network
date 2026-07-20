# Combined Acceptance Phase 44/45

Tai lieu nay danh cho Ubuntu runtime. Static test tren Windows khong thay the
duoc firewall namespace, nftables counter, NAT evidence, Mininet namespace hay
OpenFlow flow that.

## Dieu kien truoc khi chay

Topology, OS-Ken controller, FastAPI backend va React frontend phai dang chay.
Operator token nam trong `logs/operator.token`. Khong copy token vao source,
issue, screenshot hoac log.

Terminal 1, khoi dong topology/controller:

```bash
cd ~/Downloads/CCH_Network
sudo ./sdn_mpls_demo/run_topology.sh
```

Terminal 2, khoi dong dashboard:

```bash
cd ~/Downloads/CCH_Network
./scripts/start_demo.sh
```

Terminal 3, chay acceptance bang root de doc OVS, nftables va namespace:

```bash
cd ~/Downloads/CCH_Network
sudo ./scripts/phase44_45_combined_acceptance.sh
```

Script khong sua `vars/`, `sdn_mpls_demo/policy.yml`, khong tat firewall,
khong doi expected result va khong in gia tri operator token. Moi case luu
stdout, stderr, exit code, thoi gian va summary trong `runtime_reports/`.

## Noi dung duoc kiem tra

- Git/runtime baseline, Linux/root va dependency.
- Controller `6653`, backend `8000`, frontend `5173`.
- Mininet topology process, hai firewall namespace, OVS `core_hq` va `dist_telesale`.
- Hai table nftables `inet cch_filter`, forwarding va counter that.
- API hai site `hq`/`telesale`, 9 logical OVS, mapping `access_backoffice -> access_bo`, 2 CE va 2 firewall.
- Ping ALLOW `h30_01 -> h90`.
- Ping DENY `h20_01 -> h30_01` va Social DENY/counter.
- Policy reload bang ruleset source-of-truth hien tai.
- Link fail/recover that tren Mininet.
- Iperf UDP 5 giay hai lan, TCP 5 giay, Voice Quality, ping sau iperf va agent HEALTH sau iperf thong qua `dashboard_runtime_smoke_test.py`.
- Hai iperf khac destination va hai iperf cung destination phai cho ket qua BUSY dung contract.
- OpenFlow dump va runtime log safety.
- Route va NAT source capture theo Phase 44 runner. Neu NAT chua co bang chung, ket luan van la `NAT REQUIREMENT NOT YET CONCLUDED`.

## Lenh quan sat bang chung

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows core_hq
sudo ovs-ofctl -O OpenFlow13 dump-flows dist_telesale
sudo ip netns exec fw_hq nft -a list table inet cch_filter
sudo ip netns exec fw_telesale nft -a list table inet cch_filter
tail -n 120 logs/backend.log
tail -n 120 sdn_mpls_demo/runtime/controller.log
tail -n 120 sdn_mpls_demo/runtime/mininet_control_agent.log
```

## Doc ket qua

`PASS` cua script chi co nghia la cac command live da tra ket qua phu hop va
artifact da duoc luu. Tren Windows hoac khi script chua chay, dashboard phai
hien `Phase 44: pending` va khong duoc coi counter `0` la counter runtime.

Sau khi script ket thuc, giu lai:

- file `.log` tong;
- thu muc case co stdout/stderr;
- `phase44_45_combined_summary.json`;
- report Phase 44 va dashboard runtime smoke;
- `git status --short` va commit dang chay.

Khong commit thu muc `runtime_reports/`; thu muc nay da nam trong `.gitignore`.

## Don dep sau test

```bash
cd ~/Downloads/CCH_Network
./scripts/stop_demo.sh
sudo mn -c
```

Neu terminal chay topology bi dong dot ngot, hay chay cleanup roi khoi dong
lai; khong coi mot session dang mo la bang chung cho session moi.
