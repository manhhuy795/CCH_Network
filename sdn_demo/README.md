# SDN Demo - Mininet + Open vSwitch

Thu muc nay demo SDN cho he thong Call Center BPO tren Ubuntu VM.

Demo khong can thiet bi that, khong can GNS3/EVE-NG, khong can Ryu/OS-Ken. Controller hien tai la `controller_standalone_policy.py`, tu viet bang Python va noi voi Open vSwitch bang OpenFlow 1.3.

## Mo hinh

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

Policy chinh:

- h20/h30/h40 bi cach ly voi nhau.
- h20/h30/h40/h50/h60 duoc di Voice neu `voice_enabled=true`.
- h20/h30/h40/h50/h60 duoc di Zalo va Call App.
- h20/h30/h40/h50/h60 bi chan Social Media.
- h50 va h60 khong co full access hai chieu.

Day la SDN policy simulation, khong mo phong MPLS L3VPN that va khong program ISP PE/P core.

## Cai dat nhanh tren Ubuntu 22.04

Chay tu thu muc goc repo:

```bash
chmod +x sdn_demo/setup_ubuntu_vm_vi.sh
./sdn_demo/setup_ubuntu_vm_vi.sh
```

Neu muon cai xong va chay demo luon:

```bash
./sdn_demo/setup_ubuntu_vm_vi.sh --run
```

## Cai dat thu cong

```bash
sudo apt update
sudo apt install -y git python3 python3-pip python3-venv python3-yaml iperf mininet openvswitch-switch
sudo systemctl enable --now openvswitch-switch
```

Khong can tao `.venv`, khong can Python 3.12, khong can `pip install ryu`.

## Chay demo

```bash
sudo mn -c
chmod +x sdn_demo/run_demo.sh
./sdn_demo/run_demo.sh
```

Khi thay prompt nay la ban da vao lab SDN:

```text
mininet>
```

## Lenh quan trong trong Mininet

Chay test chi tiet bang mot lenh:

```bash
testsdn
```

Xem ban dang o dau trong phan SDN:

```bash
sdninfo
```

Xem policy dang duoc dung:

```bash
sdnpolicy
```

Xem flow counter va port counter cua Open vSwitch:

```bash
sdnstats
```

Do bang thong that giua hai host bang iperf:

```bash
sdnbw h20 h90 5
```

Thao tac SDN: chan/mo tam thoi mot cap host bang OpenFlow rule priority cao:

```bash
sdnblock h20 h90
h20 ping -c 2 h90      # expected fail sau khi block
sdnunblock h20 h90
h20 ping -c 2 h90      # expected pass sau khi unblock
```

Xem danh sach lenh test:

```bash
sh cat sdn_demo/test_commands.txt
```

Test thu cong:

```text
h20 ping -c 2 h30      # expected fail
h20 ping -c 2 h90      # expected pass
h20 ping -c 2 hzalo    # expected pass
h20 ping -c 2 hcall    # expected pass
h20 ping -c 2 hsocial  # expected fail
h50 ping -c 2 h60      # expected fail/limited
h50 ping -c 2 hcall    # expected pass
h50 ping -c 2 hsocial  # expected fail
```

## Xem flow va log SDN

Trong `mininet>`:

```bash
sh ovs-ofctl -O OpenFlow13 dump-flows s1
sh tail -n 80 sdn_demo/controller.log
```

Trong terminal Ubuntu khac:

```bash
tail -f sdn_demo/controller.log
```

Log controller se co dang:

```text
ALLOW policy: h20(172.10.20.10) -> h90(172.10.90.10)
DENY policy: h20(172.10.20.10) -> h30(172.10.30.10)
DENY default: ...
```

## Cleanup

Thoat Mininet:

```bash
exit
```

Don lab:

```bash
sudo mn -c
```

## File quan trong

```text
policy.yml                          Policy SDN source-of-truth
topology_callcenter.py              Topology Mininet/OVS va lenh testsdn/sdninfo
controller_standalone_policy.py     Controller OpenFlow 1.3 standalone
controller_callcenter_policy.py     Controller Ryu/OS-Ken cu, chi giu de tham khao
run_demo.sh                         Script chay demo
setup_ubuntu_vm_vi.sh               Script cai dat tieng Viet cho Ubuntu VM
test_commands.txt                   Lenh test trong Mininet
```
