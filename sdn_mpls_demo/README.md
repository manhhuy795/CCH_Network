# SDN MPLS Demo - Call Center BPO

Module này là lab **Hybrid MPLS L3VPN + SDN Edge Policy** chạy trên Ubuntu
24.04 LTS. Lab tạo 100 user thật trong Mininet, 5 service và 7 Open vSwitch
được OS-Ken Controller điều khiển bằng OpenFlow 1.3.

## Phạm vi đúng

- SDN điều khiển OVS tại access, core, distribution và service edge.
- MPLS L3VPN đóng vai trò WAN transport logic giữa HQ và Branch.
- CE Router, Firewall và MPLS Cloud là namespace/bridge mô phỏng, không chịu
  sự điều khiển của SDN Controller.
- Không triển khai MPLS provider-grade, MP-BGP, PE/P core hoặc IPSec CE-to-CE.

## Thành phần lab

| Thành phần | Số lượng |
|---|---:|
| User Dự án A/B/C | 60 |
| User Telesale/BackOffice | 40 |
| Voice/Zalo/Call App/Social/Internet | 5 |
| OVS được OS-Ken điều khiển | 7 |

Đường liên site:

```text
Branch Distribution → CE Router Branch → MPLS L3VPN Cloud
→ CE Router HQ → HQ Core SDN
```

Internet breakout:

```text
HQ user     → HQ Core → Firewall HQ → Internet Zone
Branch user → Branch Distribution → Firewall Branch → Internet Zone
```

## Ubuntu VM mới - copy/paste từ đầu

Dùng Ubuntu 24.04 LTS. Nếu vừa tạo máy ảo mới, mở Terminal 1 và chạy nguyên
block này:

```bash
cd ~/Downloads

sudo apt update
sudo apt install -y \
  git mininet openvswitch-switch iperf3 \
  python3 python3-venv python3-pip python3-dev \
  build-essential curl jq iproute2 procps util-linux \
  nodejs npm
sudo systemctl enable --now openvswitch-switch

if [ ! -d CCH_Network ]; then
  git clone https://github.com/manhhuy795/CCH_Network.git
fi

cd ~/Downloads/CCH_Network
git pull
chmod +x sdn_mpls_demo/*.sh
./sdn_mpls_demo/setup_ubuntu_24_04.sh
sudo ./sdn_mpls_demo/run_topology.sh
```

Giữ Terminal 1 ở màn hình `mininet>`. Không chạy `run_topology.sh` lần thứ hai
ở terminal khác.

## Terminal 1 - cài thư viện và chạy topology

Nếu repo đã có sẵn trên máy, chạy block ngắn này:

```bash
cd ~/Downloads/CCH_Network
git pull

# Các thư viện/package cần cho SDN lab, Mininet, Open vSwitch và dashboard.
sudo apt update
sudo apt install -y \
  git mininet openvswitch-switch iperf3 \
  python3 python3-venv python3-pip python3-dev \
  build-essential curl jq iproute2 procps util-linux \
  nodejs npm
sudo systemctl enable --now openvswitch-switch

chmod +x sdn_mpls_demo/*.sh
./sdn_mpls_demo/setup_ubuntu_24_04.sh
sudo ./sdn_mpls_demo/run_topology.sh
```

Script chỉ cài package và tạo virtualenv riêng tại
`sdn_mpls_demo/.venv`; không thay đổi Python hệ thống.

Khi thấy dấu nhắc `mininet>`, topology đã chạy. Kiểm tra nhanh:

```text
testpolicy       # chạy 8 ca ALLOW/DENY bằng ping thật
isolationflows   # xem DROP flow priority 400 trên 7 OVS
```

## Chạy lab lại sau khi đã cài xong

Cách đơn giản nhất, chỉ cần một lệnh:

```bash
sudo ./sdn_mpls_demo/run_topology.sh
```

Chỉ chạy topology ở **một terminal duy nhất**. Không chạy lại lệnh trên ở
terminal thứ hai vì một VM không thể tạo hai bộ interface Mininet trùng tên.

Script sẽ:

1. Kiểm tra virtualenv và module OS-Ken.
2. Kiểm tra cổng OpenFlow `6653`.
3. Tự chạy controller nếu cổng chưa có listener.
4. Chờ controller sẵn sàng rồi mới tạo topology.
5. In `runtime/controller.log` nếu controller không khởi động được.

Nếu muốn chạy controller thủ công để xem log trực tiếp thì dùng cách nâng cao:

```bash
# Terminal 1
./sdn_mpls_demo/run_controller.sh

# Terminal 2
sudo ./sdn_mpls_demo/run_topology.sh
```

Sau khi topology hiện dấu nhắc `mininet>`, mở terminal mới để chạy dashboard:

```bash
# Terminal 2: backend
./dashboard/run_live_dashboard.sh

# Terminal 3: frontend
cd dashboard/frontend
npm install
npm run dev -- --host 0.0.0.0
```

Khi thấy `mininet>`, dùng các lệnh trong
`sdn_mpls_demo/test_commands.txt`.

Kiểm tra nhanh segmentation bằng traffic thật:

```text
testpolicy       # chạy 8 ca ALLOW/DENY
isolationflows   # xem DROP flow priority 400 trên 7 OVS
```

Terminal 3, chạy backend:

```bash
cd dashboard/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo -E .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Terminal 4, chạy frontend:

```bash
cd dashboard/frontend
npm install
npm run dev -- --host 0.0.0.0
```

Mở `http://<IP-Ubuntu-VM>:5173`.

## Dọn lab

Thoát Mininet bằng `exit`, sau đó:

```bash
./sdn_mpls_demo/cleanup.sh
```

## Dữ liệu runtime

- `runtime/installed_flows.json`: flow do controller đã cài.
- `runtime/events.jsonl`: nhật ký quyết định allow/drop.
- Hai file này được sinh khi chạy và không phải source-of-truth.

Source-of-truth nằm tại `sdn_mpls_demo/policy.yml`.

## Phiên bản Ubuntu

Không cần hạ xuống Ubuntu cũ hơn. Module này dành cho Ubuntu 24.04 LTS và
Python 3.12. Module `sdn_demo/` cũ mới là lựa chọn tương thích Ubuntu 22.04.

Project pin `os-ken==3.1.1`. Không nâng lên OS-Ken 4.x vì upstream đã xóa
`osken-manager` và module `os_ken.cmd`; hai thành phần này cần để chạy
OpenFlow Controller độc lập trong lab.

Nếu controller không lên:

```bash
tail -n 80 sdn_mpls_demo/runtime/controller.log
sudo ss -ltnp | grep :6653
sdn_mpls_demo/.venv/bin/python -c "import os_ken.cmd.manager; print('OS-Ken CLI OK')"
sdn_mpls_demo/.venv/bin/pip show os-ken | grep Version
```
