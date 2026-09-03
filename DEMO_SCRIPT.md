# Demo Full-SDN trong 5–10 phút

Kịch bản này dùng Ubuntu 24.04 đã chạy `sdn_mpls_demo/setup_ubuntu_24_04.sh`. Mở bốn terminal tại root repository. Không dùng output tĩnh để thay cho bằng chứng live.

## 0. Chuẩn bị

```bash
cd ~/CCH_Network
sudo mn -c
chmod +x sdn_mpls_demo/*.sh scripts/*.sh
```

Thông điệp mở đầu gợi ý:

> Đây là mô hình mạng doanh nghiệp Full-SDN gồm 6 OVS do OS-Ken điều khiển bằng OpenFlow 1.3. Fabric dùng pipeline bốn bảng, default-deny và explicit forwarding; không dùng OFPP_NORMAL.

## 1. Khởi động controller và topology — 1 phút

Terminal 1:

```bash
./sdn_mpls_demo/run_controller.sh
```

Terminal 2:

```bash
sudo ./sdn_mpls_demo/run_topology.sh
```

Giữ Terminal 2 tại prompt `mininet>`.

## 2. Chứng minh 6 OVS đã kết nối — 30 giây

Terminal 3:

```bash
for sw in access_floor1 access_floor2 core_hq access_branch dist_branch infra_access; do
  controller_uuid="$(sudo ovs-vsctl --data=bare --no-heading get Bridge "$sw" controller | tr -d '[]')"
  connected="$(sudo ovs-vsctl --data=bare --no-heading get Controller "$controller_uuid" is_connected)"
  printf '%-16s %s\n' "$sw" "$connected"
done
```

Kỳ vọng: đúng 6 dòng và tất cả trả `true`.

## 3. Chứng minh không có `OFPP_NORMAL` — 30 giây

```bash
for sw in access_floor1 access_floor2 core_hq access_branch dist_branch infra_access; do
  sudo ovs-ofctl -O OpenFlow13 dump-flows "$sw"
done | tee /tmp/cch-flows.txt

if grep -q 'actions=NORMAL' /tmp/cch-flows.txt; then
  echo 'FAIL: found OFPP_NORMAL'
else
  echo 'PASS: zero OFPP_NORMAL across all 6 OVS'
fi
```

## 4. Show pipeline `0 → 10 → 20 → 30` — 45 giây

```bash
for table in 0 10 20 30; do
  echo "===== TABLE $table ====="
  sudo ovs-ofctl -O OpenFlow13 dump-flows access_floor1 "table=$table" | head -n 12
done
```

Chỉ vào các action `goto_table:10`, `goto_table:20`, `goto_table:30`, các rule drop và output port tường minh.

## 5. Segmentation và least privilege — 1–2 phút

Tại prompt `mininet>`:

```text
h101_01 ping -c 3 10.10.101.12
h101_01 ping -c 3 10.10.103.11
guest_01 ping -c 3 10.250.20.30
guest_01 ping -c 3 10.10.101.11
iot_cam_01 ping -c 3 10.10.100.14
iot_cam_01 ping -c 3 10.250.20.30
h110_01 ping -c 3 10.10.101.11
h101_01 ping -c 3 10.10.110.11
```

Kỳ vọng:

| Case | Kết quả |
|---|---|
| Same Project 1 | PASS |
| Project 1 → Project 3 | DROP |
| Guest → General Internet | PASS |
| Guest → internal Project | DROP |
| IoT → NMS | PASS |
| IoT → Internet | DROP |
| IT Support → managed user | PASS |
| User → IT Support | DROP |

## 6. DHCP DORA — 45 giây

Nếu máy chưa có DHCP client/server tools, cài một lần: `sudo apt install -y dnsmasq isc-dhcp-client`.

Terminal 3:

```bash
sudo truncate -s 0 /tmp/dnsmasq.log
GUEST_PID="$(pgrep -f 'mininet:guest_01' | head -n 1)"
sudo mnexec -a "$GUEST_PID" ip addr flush dev h120u01-eth0
sudo mnexec -a "$GUEST_PID" timeout 10 dhclient -v -1 h120u01-eth0
sudo tail -n 30 /tmp/dnsmasq.log
```

Trình bày đủ `DHCPDISCOVER → DHCPOFFER → DHCPREQUEST → DHCPACK`, lease thuộc dải `10.10.120.150–199`, relay từ access port tới `hdhcp` (`10.10.100.10`) và response quay về đúng client attachment. Nếu thiếu một bước hoặc không có lease thật, kết luận `BLOCKED`, không đổi thành PASS.

## 7. VLAN 93 Primary/Backup failover — 1 phút

Terminal 3:

```bash
sudo -E sdn_mpls_demo/.venv/bin/python scripts/test_mpls_failover_runtime.py
```

Hoặc thao tác trên Dashboard: fail attachment link `core_hq-ce_hq1`, quan sát Primary down, Backup active và ping `h93_01 → h93_11` vẫn PASS; sau đó recover Primary. Gọi đúng là **automatic attachment-link failover**, không tuyên bố carrier-grade hoặc hội tụ tức thời.

## 8. Dashboard — 1 phút

Terminal 4:

```bash
./scripts/start_demo.sh
```

Mở `http://127.0.0.1:5173` và lần lượt chỉ ra:

- health của controller, 6 OVS, backend và control agent;
- topology HQ/Branch/Infra/Firewall/Internet;
- VLAN 93 Primary/Backup và điều khiển fail/recover;
- flow tables/pipeline, policy decision và event log;
- preflight/live evidence, không dùng mock để kết luận runtime PASS.

## 9. Unit + live tests — 1 phút

```bash
# Không cần root/Mininet: đúng 24 Full-SDN unit cases
sdn_mpls_demo/.venv/bin/python -m pytest -q tests/test_full_sdn_fabric.py

# Cần topology/controller đang chạy: đúng 27 traffic cases
sudo -E sdn_mpls_demo/.venv/bin/python sdn_mpls_demo/run_live_tests.py
```

Kết thúc khi thấy `24 passed` và `Passed Test Cases: 27 / 27`. Nhắc rõ live result chỉ có giá trị cho lần chạy Ubuntu hiện tại.

## Cleanup

```bash
./scripts/stop_demo.sh
sudo mn -c
```
