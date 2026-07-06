# CCH Network Automation - Call Center BPO

Repo này dùng để demo và triển khai mô hình **Network-as-Code** cho hệ thống
Call Center BPO hai site. Repo có hai phần chính:

- **Network Automation truyền thống**: validate YAML, render config Cisco-like,
  backup, dry-run deploy, verify và rollback.
- **SDN Simulation Demo**: chạy thật trên Ubuntu VM bằng Mininet + Open vSwitch
  + OS-Ken/Ryu, không cần thiết bị vật lý.

## Khuyến Nghị Python

Để chạy ổn định nhất, nên dùng:

- **Ubuntu 24.04 LTS + Python 3.12**: khuyến nghị chính cho repo này.

Không khuyến nghị dùng Python quá mới như **Python 3.14** cho SDN demo, vì
OS-Ken/Ryu có thể chưa tương thích tốt.

Kiểm tra Python:

```bash
python3.12 --version
```

## Cấu Trúc Repo

```text
inventories/             Inventory mẫu cho Ansible/Netmiko
vars/                    Source-of-truth YAML
templates/               Jinja2 templates
generated_configs/       Config/policy được render
backups/                 Backup config thiết bị
playbooks/               Ansible playbooks
scripts/                 Python automation scripts
tests/                   Unit tests
docs/                    Tài liệu thiết kế
sdn_demo/                Demo SDN bằng Mininet/Open vSwitch
```

## Cài Đặt Trên Ubuntu VM

Nếu chỉ muốn chạy automation offline:

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip git

git clone https://github.com/manhhuy795/CCH_Network.git
cd CCH_Network

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Chạy kiểm tra offline:

```bash
python scripts/validate_vars.py
python scripts/generate_configs.py
python scripts/verify_network.py
python scripts/generate_sdn_policies.py
pytest
```

Kết quả mong đợi:

```text
Validation passed.
Rendered 11 files
Offline verify passed.
Rendered SDN intent policy: ...
tests passed
```

## Chạy SDN Simulation Demo Trên Ubuntu VM

Đây là phần demo SDN thực tế, không cần GNS3/EVE-NG hay thiết bị thật.

### Cách Nhanh Nhất

```bash
cd CCH_Network
git pull

chmod +x sdn_demo/setup_ubuntu_vm_vi.sh
./sdn_demo/setup_ubuntu_vm_vi.sh
```

Sau khi script cài xong, chạy demo:

```bash
source .venv/bin/activate
./sdn_demo/run_demo.sh
```

Nếu muốn cài xong chạy demo luôn:

```bash
./sdn_demo/setup_ubuntu_vm_vi.sh --run
```

### Lệnh Cài Thủ Công

```bash
sudo apt update
sudo apt install -y \
  git \
  python3.12 \
  python3.12-venv \
  python3-pip \
  python3-yaml \
  mininet \
  openvswitch-switch

sudo systemctl enable --now openvswitch-switch

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r sdn_demo/requirements.txt
```

Nếu OS-Ken lỗi, thử Ryu:

```bash
source .venv/bin/activate
pip install ryu PyYAML
```

Nếu `apt` không tìm thấy `python3.12`, nên dùng Ubuntu 24.04 LTS hoặc cài Python
3.12 từ nguồn package phù hợp với bản Ubuntu của bạn.

## Lệnh Test Trong Mininet

Khi chạy `./sdn_demo/run_demo.sh`, nếu thấy prompt:

```text
mininet>
```

hãy copy/paste từng lệnh sau:

```text
h20 ping -c 2 h30      # mong đợi fail
h20 ping -c 2 h90      # mong đợi pass
h20 ping -c 2 hzalo    # mong đợi pass
h20 ping -c 2 hcall    # mong đợi pass
h20 ping -c 2 hsocial  # mong đợi fail
h50 ping -c 2 h60      # mong đợi fail/limited
h50 ping -c 2 hcall    # mong đợi pass
h50 ping -c 2 hsocial  # mong đợi fail
```

Xem log controller:

```bash
tail -f sdn_demo/controller.log
```

Dọn Mininet khi cần:

```bash
sudo mn -c
```

## SDN Demo Mô Phỏng Gì?

Topology Mininet gồm:

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
```

Policy:

- `h20` không truy cập được `h30/h40`.
- `h30` không truy cập được `h20/h40`.
- `h40` không truy cập được `h20/h30`.
- `h20/h30/h40/h50/h60` truy cập được `h90` nếu `voice_enabled=true`.
- `h20/h30/h40/h50/h60` truy cập được `hzalo`.
- `h20/h30/h40/h50/h60` truy cập được `hcall`.
- `h20/h30/h40/h50/h60` không truy cập được `hsocial`.
- `h50` và `h60` không mở full access hai chiều.

Lưu ý: đây là **SDN policy simulation**, không mô phỏng MPLS L3VPN thật, không
tạo CE-to-CE route, không program ISP MPLS PE/P core.

## Network Automation Workflow

Validate biến YAML:

```bash
python scripts/validate_vars.py
```

Sinh config:

```bash
python scripts/generate_configs.py
```

Verify offline:

```bash
python scripts/verify_network.py
```

Dry-run deploy:

```bash
python scripts/deploy_configs.py --generate
```

Backup dry-run:

```bash
python scripts/backup_configs.py --dry-run
```

Các lệnh live dưới đây chỉ chạy khi có GNS3/EVE-NG/thiết bị thật và đã sửa IP
trong `inventories/lab_inventory.yml`:

```bash
export CONFIRM_DEPLOY=true
python scripts/backup_configs.py --inventory inventories/lab_inventory.yml
python scripts/deploy_configs.py --inventory inventories/lab_inventory.yml --apply
python scripts/verify_network.py --live --inventory inventories/lab_inventory.yml
```

## Cảnh Báo An Toàn

- Không deploy production trước khi test lab.
- Không hardcode username/password; dùng `.env`.
- Deploy thật yêu cầu `CONFIRM_DEPLOY=true`.
- Phải backup trước khi deploy.
- Firewall Zalo/Call App chỉ là placeholder, cần cập nhật FQDN/App-ID/IP/port
  thực tế.
- Voice/Mgmt switch là SPOF kép.
- CE/uplink đơn là SPOF WAN.
- MPLS L3VPN do ISP vận hành, MP-BGP trong MPLS core ngoài phạm vi công ty.

## Tài Liệu

- `sdn_demo/README.md`
- `docs/sdn_mininet_demo.md`
- `docs/topology.md`
- `docs/routing_design.md`
- `docs/acl_design.md`
- `docs/firewall_policy.md`
- `docs/sdn_design.md`
- `docs/gns3_lab.md`
