# Thiết kế SDN trong repository

Repository có hai lớp SDN khác nhau và không nên gọi lẫn nhau.

## Lớp SDN intent của Network Automation

Các file `vars/sdn.yml`, template intent và
`scripts/generate_sdn_policies.py` sinh policy JSON cho quy trình automation.
Chế độ `generic_rest` chỉ là điểm tích hợp API mẫu; tự nó không phải OpenFlow
Controller và không chứng minh dataplane đã được lập trình.

## Lab SDN runtime

`sdn_mpls_demo/` là demo SDN chạy thật:

- OS-Ken Controller.
- OpenFlow 1.3.
- 7 Open vSwitch.
- 104 user + 5 service trong Mininet.
- Flow allow/drop được cài và đọc lại bằng `ovs-ofctl`.

## Quan hệ với MPLS

SDN không thay thế và không điều khiển MPLS Core. MPLS L3VPN đóng vai trò WAN
transport giữa HQ và Branch:

```text
HQ Core → CE HQ → MPLS L3VPN Cloud → CE Branch → Branch Distribution
```

Trong lab, CE/MPLS là namespace/bridge mô phỏng đường vận chuyển, không phải
provider-grade MPLS hoặc MP-BGP.

Xem hướng dẫn đầy đủ tại:

- `sdn_mpls_demo/README.md`
- `sdn_mpls_demo/docs/sdn_design_vi.md`
- `sdn_mpls_demo/docs/demo_script_vi.md`
