# CCH Network Automation - Call Center BPO

Repo nay demo Network Automation va SDN cho he thong Call Center BPO hai site.

## Thanh phan chinh

```text
vars/                    Source-of-truth YAML
templates/               Jinja2 templates sinh cau hinh
scripts/                 Script validate/render/verify/deploy/backup
playbooks/               Ansible workflow mau
generated_configs/       Cau hinh da render
sdn_demo/                Mininet + Open vSwitch + standalone OpenFlow controller
dashboard/               SDN live web dashboard thao tac voi Mininet that
tests/                   Unit tests
docs/                    Tai lieu thiet ke
```

## Automation offline

```bash
python -m venv .venv
source .venv/bin/activate        # Linux
# .venv\\Scripts\\activate       # Windows PowerShell
pip install -r requirements.txt
cp .env.example .env

python scripts/validate_vars.py
python scripts/generate_configs.py
python scripts/verify_network.py
python scripts/generate_sdn_policies.py
pytest
```

## SDN Mininet demo tren Ubuntu VM

Khong can thiet bi that, khong can Ryu/OS-Ken, khong can Python 3.12.

```bash
sudo apt update
sudo apt install -y git python3 python3-pip python3-yaml iperf mininet openvswitch-switch
sudo systemctl enable --now openvswitch-switch

git clone https://github.com/manhhuy795/CCH_Network.git
cd CCH_Network

sudo mn -c
./sdn_demo/run_demo.sh
```

Khi thay prompt:

```text
mininet>
```

co the chay:

```text
testsdn
sdninfo
sdnstats
sdnbw h20 h90 5
h20 ping -c 2 h90
h20 ping -c 2 h30
```

## SDN live web dashboard

Terminal 1: giu Mininet dang chay:

```bash
cd ~/Downloads/CCH_Network
sudo mn -c
./sdn_demo/run_demo.sh
```

Terminal 2: chay web dashboard:

```bash
cd ~/Downloads/CCH_Network
chmod +x dashboard/run_live_dashboard.sh
./dashboard/run_live_dashboard.sh
```

Mo trinh duyet:

```text
http://127.0.0.1:8000
```

Neu mo tu Windows host vao Ubuntu VM:

```text
http://<ubuntu-vm-ip>:8000
```

Dashboard có:

- Sơ đồ mạng dựng bằng SVG với các node và liên kết độc lập.
- Gói tin chạy tuần tự qua từng node, dừng đúng điểm policy khi bị chặn.
- Ping và đo băng thông TCP/UDP trực tiếp trong namespace Mininet.
- Đo KPI Call Center: RTT, jitter, mất gói, thông lượng, R-factor và MOS.
- Bảng OpenFlow đã diễn giải để dễ đọc hơn kết quả thô từ `ovs-ofctl`.
- Nút chặn/gỡ chặn bằng OpenFlow rule ưu tiên cao.

## Policy SDN demo

```text
h20      Project A              172.10.20.10/24
h30      Project B              172.10.30.10/24
h40      Project C              172.10.40.10/24
h50      Telesale               172.10.50.10/24
h60      Branch Admin           172.10.60.10/24
h90      Voice service          172.10.90.10/24
hzalo    Zalo simulator         172.10.200.10/24
hcall    Call App simulator     172.10.201.10/24
hsocial  Social Media simulator 172.10.202.10/24
hinternet Internet test          172.10.203.10/24
```

Policy:

- h20/h30/h40 bi cach ly voi nhau.
- h50 va h60 khong mo full access hai chieu.
- h20/h30/h40/h50/h60 duoc truy cap h90 khi `voice_enabled=true`.
- h20/h30/h40/h50/h60 duoc truy cap hzalo va hcall.
- h20/h30/h40/h50/h60 được truy cập Internet chung (`hinternet`).
- h20/h30/h40/h50/h60 bi chan hsocial.
- h50 được truy cập h20 có kiểm soát; đường logic liên site đi qua CE Branch,
  MPLS L3VPN Cloud và CE HQ.

Đây là SDN edge-policy simulation trên Mininet/OVS. MPLS L3VPN được thể hiện
như WAN transport logic do ISP quản lý; demo không lập trình PE/P core.

## Cleanup

```bash
sudo mn -c
```

## Tai lieu

- `sdn_demo/README.md`
- `dashboard/README.md`
- `docs/sdn_mininet_demo.md`
- `docs/topology.md`
- `docs/routing_design.md`
- `docs/firewall_policy.md`
