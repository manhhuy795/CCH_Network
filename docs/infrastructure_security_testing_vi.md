# Kiểm thử bảo mật hạ tầng

Bộ kiểm thử này bổ sung cho `testpolicy` và smoke test dashboard. Nó tập trung
vào các kiểm soát đang có trong mô hình hai site hiện tại:

- cô lập Project A/B/C và Telesale/BackOffice;
- IT Support chỉ có quyền hỗ trợ được khai báo, user thường không chủ động tới VLAN 70;
- Social Media bị chặn tại firewall stateful, kể cả IT Support;
- Internet/Service Zone không được mở kết nối mới vào user nội bộ;
- Voice path không đi qua firewall Internet;
- isolation DROP chỉ được enforce tại `core_hq` và `dist_telesale`;
- VLAN 10 Management, IP/subnet, 110 user, 5 service và 9 OVS;
- nftables forward/input default drop, established/related, invalid drop và counters.

## Kiểm tra tĩnh trên Windows hoặc Ubuntu

```bash
python scripts/infrastructure_security_check.py
```

Lệnh này đánh giá source-of-truth và policy engine. Kết quả `PASS` không có
nghĩa OVS hoặc Mininet đang chạy.

## Kiểm tra runtime thật trên Ubuntu

Topology và Control Agent phải đang hoạt động:

```bash
sudo ./scripts/infrastructure_security_runtime_check.sh
```

Script dùng Unix socket Control Agent để ping thật; đọc flow từ OVS; đọc
`FIREWALL_STATUS`; rồi xác nhận counter `social_deny` và `inbound_deny` tăng
sau traffic bị chặn. Token control agent không được in vào log.

Artifact:

```text
runtime_reports/infrastructure_security_<timestamp>.log
runtime_reports/infrastructure_security_<timestamp>.json
```

## Ma trận chính

| Case | Expected |
|---|---|
| `h20_01 -> h30_01`, `h20_01 -> h40_01` | DENY tại `core_hq` |
| `h50_01 <-> h60_01` | DENY tại edge SDN tương ứng |
| `h20_01 -> h90`, `h50_01 -> h90` | ALLOW; không qua firewall Internet |
| `h70_01 -> h20_01` | ALLOW để hỗ trợ |
| `h20_01 -> h70_01` | DENY tại `core_hq` |
| `h20_01 -> hsocial`, `h70_01 -> hsocial` | DENY tại `fw_hq` |
| `hinternet -> h20_01` | DENY tại `fw_hq` |
| `hsocial -> h50_01` | DENY tại `fw_telesale` |

## Lệnh Mininet bổ sung

```text
testpolicy
isolationflows
firewallrules
reloadfirewall
```

Không dùng static result để tuyên bố runtime PASS. Nếu runtime checker FAIL,
lưu JSON/log và đối chiếu `controller.log`, `mininet_control_agent.log`, flow
OpenFlow và nftables counters.
