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

## Cài đặt

```bash
cd ~/Downloads/CCH_Network
chmod +x sdn_mpls_demo/*.sh
./sdn_mpls_demo/setup_ubuntu_24_04.sh
```

Script chỉ cài package và tạo virtualenv riêng tại
`sdn_mpls_demo/.venv`; không thay đổi Python hệ thống.

## Chạy lab

Cách đơn giản nhất, chỉ cần một lệnh:

```bash
sudo ./sdn_mpls_demo/run_topology.sh
```

Script sẽ:

1. Kiểm tra virtualenv và module OS-Ken.
2. Kiểm tra cổng OpenFlow `6653`.
3. Tự chạy controller nếu cổng chưa có listener.
4. Chờ controller sẵn sàng rồi mới tạo topology.
5. In `runtime/controller.log` nếu controller không khởi động được.

Nếu muốn chạy controller thủ công để xem log trực tiếp:

```bash
# Terminal 1
./sdn_mpls_demo/run_controller.sh

# Terminal 2
sudo ./sdn_mpls_demo/run_topology.sh
```

Khi thấy `mininet>`, dùng các lệnh trong
`sdn_mpls_demo/test_commands.txt`.

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

Nếu controller không lên:

```bash
tail -n 80 sdn_mpls_demo/runtime/controller.log
sudo ss -ltnp | grep :6653
sdn_mpls_demo/.venv/bin/python -c "import os_ken; print('OS-Ken OK')"
```
