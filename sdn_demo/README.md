# SDN Demo - Mininet + Open vSwitch + OS-Ken/Ryu

Thư mục này dùng để demo SDN thực tế trên Ubuntu VM. Demo không cần thiết bị
mạng thật, không cần GNS3/EVE-NG, và không phụ thuộc firewall/router vật lý.

Controller dùng OpenFlow 1.3 để điều khiển Open vSwitch:

- Cách ly Project A/B/C.
- Cho phép truy cập Voice nếu `voice_enabled=true`.
- Cho phép Zalo simulator.
- Cho phép Call App simulator.
- Chặn Social Media simulator.
- Không mở full access hai chiều giữa Telesale và Branch Admin.

Đây chỉ là **SDN policy simulation**. Demo không mô phỏng MPLS L3VPN thật, không
tạo logic CE-to-CE, và không program ISP MPLS PE/P core.

## Khuyến Nghị Môi Trường

Nên dùng:

- Ubuntu 22.04 LTS với Python 3.10.
- Ubuntu 24.04 LTS với Python 3.12.

Không khuyến nghị Python 3.14 vì OS-Ken/Ryu có thể chưa tương thích ổn định.

## Topology

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

Demo dùng một Open vSwitch trung tâm. Vì các host nằm ở nhiều subnet `/24`,
topology sẽ đặt default gateway giả và static ARP. Controller sẽ rewrite MAC và
đẩy packet ra đúng port dựa trên policy.

## Cài Đặt Nhanh Bằng Script Tiếng Việt

Chạy từ thư mục gốc repo:

```bash
chmod +x sdn_demo/setup_ubuntu_vm_vi.sh
./sdn_demo/setup_ubuntu_vm_vi.sh
```

Cài xong và chạy demo luôn:

```bash
./sdn_demo/setup_ubuntu_vm_vi.sh --run
```

## Cài Đặt Thủ Công

```bash
sudo apt update
sudo apt install -y \
  git \
  python3 \
  python3-pip \
  python3-venv \
  python3-yaml \
  mininet \
  openvswitch-switch

sudo systemctl enable --now openvswitch-switch

python3 -m venv .venv
source .venv/bin/activate
pip install -r sdn_demo/requirements.txt
```

Nếu OS-Ken lỗi, thử Ryu:

```bash
source .venv/bin/activate
pip install ryu PyYAML
```

Nếu cả OS-Ken và Ryu đều lỗi trên Python quá mới, hãy dùng Ubuntu 22.04/24.04
hoặc thử:

```bash
sudo apt install -y python3-ryu
```

## Chạy Demo

```bash
source .venv/bin/activate
./sdn_demo/run_demo.sh
```

Script sẽ:

1. Dọn Mininet cũ bằng `sudo mn -c`.
2. Chạy OS-Ken/Ryu controller ở `127.0.0.1:6653`.
3. Chạy topology Mininet.
4. Ghi log controller vào `sdn_demo/controller.log`.

Nếu controller lỗi, xem log:

```bash
cat sdn_demo/controller.log
```

## Lệnh Test Trong Mininet

Khi thấy:

```text
mininet>
```

copy/paste từng lệnh:

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

Các lệnh này cũng có trong:

```bash
cat sdn_demo/test_commands.txt
```

## Xem Log Controller

Mở terminal khác:

```bash
tail -f sdn_demo/controller.log
```

Log sẽ có dạng:

```text
ALLOW policy: h20(172.10.20.10) -> h90(172.10.90.10)
DENY policy: h20(172.10.20.10) -> h30(172.10.30.10)
DENY default: ...
```

## Cleanup

```bash
sudo mn -c
```

## File Quan Trọng

```text
policy.yml                         Policy SDN source-of-truth
topology_callcenter.py             Topology Mininet/OVS
controller_callcenter_policy.py    Controller OS-Ken/Ryu OpenFlow 1.3
run_demo.sh                        Script chạy demo
setup_ubuntu_vm_vi.sh              Script cài đặt tiếng Việt cho Ubuntu VM
test_commands.txt                  Lệnh test trong Mininet
```
