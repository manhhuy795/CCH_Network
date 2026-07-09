# SDN Demo nhỏ - Ubuntu 22.04

Đây là module legacy dùng một Open vSwitch trung tâm và controller OpenFlow
tối giản viết bằng Python. Module được giữ lại để không phá quy trình demo cũ.

Lab Hybrid MPLS L3VPN, OS-Ken và 100 user mới nằm tại
`sdn_mpls_demo/`.

## Phạm vi

- 5 host đại diện cho các nhóm VLAN.
- Voice, Zalo, Call App, Social Media và Internet test.
- Một OVS `s1`, OpenFlow 1.3.
- Controller standalone không phụ thuộc Ryu/OS-Ken.
- Không mô phỏng MPLS provider-grade.

## Cài đặt và chạy

```bash
cd ~/Downloads/CCH_Network
chmod +x sdn_demo/setup_ubuntu_vm_vi.sh sdn_demo/run_demo.sh
./sdn_demo/setup_ubuntu_vm_vi.sh
./sdn_demo/run_demo.sh
```

Khi thấy `mininet>`, chạy:

```text
testsdn
sdninfo
sdnpolicy
sdnstats
sdnbw h20 h90 5
```

Các phép thử chính:

```text
h20 ping -c 2 h30       # mong đợi fail
h20 ping -c 2 h90       # mong đợi pass
h20 ping -c 2 hzalo     # mong đợi pass
h20 ping -c 2 hcall     # mong đợi pass
h20 ping -c 2 hsocial   # mong đợi fail
h50 ping -c 2 h60       # mong đợi fail
h50 ping -c 2 h20       # mong đợi pass có kiểm soát
```

## Source-of-truth

- `policy.yml`: host, IP và policy.
- `controller_standalone_policy.py`: controller OpenFlow tối giản.
- `topology_callcenter.py`: topology Mininet.
- `test_commands.txt`: lệnh kiểm thử.

IP của module cũ cũng đã được chuẩn hóa sang dải private `172.16.0.0/16`.

## Cleanup

```bash
sudo mn -c
```
