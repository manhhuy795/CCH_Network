# Kế hoạch VLAN Enterprise

## Quyết định VLAN

VLAN 10 đang được dùng cho Management nên không tái sử dụng cho IoT/UPS.
Enterprise extension dùng các VLAN chưa có trong mô hình cũ:

| VLAN | Zone | Subnet | Gateway | Switch runtime |
|---:|---|---|---|---|
| 80 | Guest | `172.16.80.0/24` | `172.16.80.1` | `access_guest` |
| 100 | Infrastructure Services | `172.16.100.0/24` | `172.16.100.1` | `infra_access` |
| 110 | IoT/UPS | `172.16.110.0/24` | `172.16.110.1` | `access_iot` |

Các subnet không overlap với VLAN hiện hữu 10, 20, 30, 40, 50, 60, 70 và 90.
Mỗi zone có access switch riêng, uplink trunk riêng và được route qua `core_hq`.

## Endpoint

- Guest: `guest_01` đến `guest_04`.
- IoT/UPS: `iot_cam_01`, `iot_cam_02`, `iot_door_01`, `ups_core_01`, `ups_core_02`.
- Infrastructure: `hdhcp`, `hdns`, `hntp`, `hmonitor` trên VLAN 100.

Tổng inventory được giữ nhất quán: 110 user doanh nghiệp + 5 service hiện hữu
+ 9 Guest/IoT/UPS endpoint + 4 infrastructure service = 128 endpoint.

## Policy least privilege

- Guest chỉ được dùng DHCP/DNS/NTP và `hinternet`; không truy cập corporate,
  IT, Voice, IoT/UPS hoặc service inbound.
- IoT/UPS chỉ được dùng DHCP/DNS/NTP/Monitoring; không truy cập corporate,
  Guest, Voice hoặc Internet.
- IT Support có quyền quản trị IoT/UPS theo policy, không được bypass chặn
  Social Media.
- Kết nối mới từ Internet/service vào endpoint nội bộ bị firewall stateful chặn.

## Giới hạn lab

Các tiến trình DHCP/DNS/NTP/Monitoring trong Mininet là simulator để quan sát
namespace, reachability và policy. Đây chưa phải triển khai appliance hoặc
dịch vụ production. Khi chạy Ubuntu, xác minh VLAN thật bằng:

```bash
sudo ovs-vsctl list-ports access_iot
sudo ovs-vsctl list port iot-u01
sudo ovs-vsctl list port core-eth08
ip -d link show hq_l3-eth0.110
```

Test policy source-of-truth và topology:

```bash
python3 scripts/validate_vars.py
python3 scripts/verify_network.py
python3 -m pytest -q tests/test_enterprise_vlan_extension.py
```
