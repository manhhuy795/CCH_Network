# Phase 44 - Ubuntu Firewall Runtime Checkpoint

Phase 44 chỉ hoàn tất sau khi chạy thật trên Ubuntu 24.04 với Mininet, OVS,
OS-Ken và nftables. Static test trên Windows không thay thế checkpoint này.

## Chuẩn bị

```bash
cd ~/Downloads/CCH_Network
git fetch origin
git switch feature/dual-branch-topology
git pull --ff-only origin feature/dual-branch-topology
git branch --show-current
git rev-parse --short HEAD
git status --short

chmod +x sdn_mpls_demo/*.sh scripts/*.sh
./sdn_mpls_demo/setup_ubuntu_24_04.sh
```

## Terminal 1 - topology sạch

```bash
cd ~/Downloads/CCH_Network
sudo pkill -f 'topology_hybrid_sdn.py' || true
sudo pkill -f 'osken-manager.*controller_policy.py' || true
sudo mn -c
sudo CCH_AUTO_TEST_POLICY=0 ./sdn_mpls_demo/run_topology.sh
```

Giữ terminal tại `mininet>`. Topology phải báo nftables active trên đúng
`fw_hq` và `fw_telesale`.

Các lệnh kiểm tra trực tiếp trong Mininet:

```text
firewallrules
reloadfirewall
testpolicy
isolationflows
```

## Terminal 2 - checkpoint tự động

```bash
cd ~/Downloads/CCH_Network
sudo -E sdn_mpls_demo/.venv/bin/python scripts/phase44_firewall_runtime_check.py
echo "EXIT_CODE=$?"
```

Script không giả PASS khi `nft`, agent, ping, counter, reload, route hoặc
`tcpdump` lỗi. Artifact được lưu tại:

```text
runtime_reports/phase44_firewall_<timestamp>.log
runtime_reports/phase44_firewall_<timestamp>.json
```

## Evidence thủ công bắt buộc

```bash
sudo ip netns list
sudo ip netns exec fw_hq nft -a list table inet cch_filter
sudo ip netns exec fw_telesale nft -a list table inet cch_filter
sudo ip netns exec fw_hq sysctl net.ipv4.ip_forward
sudo ip netns exec fw_telesale sysctl net.ipv4.ip_forward
sudo ovs-ofctl -O OpenFlow13 dump-flows core_hq | grep 'cookie=0x1002'
sudo ovs-ofctl -O OpenFlow13 dump-flows dist_telesale | grep 'cookie=0x1002'
```

Chỉ hai namespace firewall được có table `inet cch_filter`:

```bash
for ns in fw_hq fw_telesale; do
  sudo ip netns exec "$ns" nft list table inet cch_filter
done
```

Kiểm tra idempotence:

```bash
before_hq=$(sudo ip netns exec fw_hq nft -a list chain inet cch_filter forward | grep -c 'handle')
before_tel=$(sudo ip netns exec fw_telesale nft -a list chain inet cch_filter forward | grep -c 'handle')
sudo -E sdn_mpls_demo/.venv/bin/python sdn_mpls_demo/firewall_nftables.py --apply
after_hq=$(sudo ip netns exec fw_hq nft -a list chain inet cch_filter forward | grep -c 'handle')
after_tel=$(sudo ip netns exec fw_telesale nft -a list chain inet cch_filter forward | grep -c 'handle')
printf 'fw_hq before=%s after=%s\n' "$before_hq" "$after_hq"
printf 'fw_telesale before=%s after=%s\n' "$before_tel" "$after_tel"
```

## Connectivity matrix

Tại `mininet>`:

```text
h20_01 ping -c 3 hcall
h20_01 ping -c 3 hzalo
h20_01 ping -c 3 hsocial
h60_01 ping -c 3 hcall
h60_01 ping -c 3 hzalo
h60_01 ping -c 3 hsocial
h50_01 ping -c 3 hcall
h50_01 ping -c 3 hzalo
h50_01 ping -c 3 hsocial
hinternet ping -c 3 h20_01
hinternet ping -c 3 h60_01
hinternet ping -c 3 h50_01
h60_01 ping -c 3 h90
h50_01 ping -c 3 h90
h50_01 ping -c 3 h60_01
h60_01 ping -c 3 h50_01
```

Call/Zalo/Voice phải ALLOW. Social và inbound Internet phải bị nftables DROP.
Hai hướng Telesale/BackOffice phải tiếp tục hit OpenFlow cookie `0x1002`,
priority `400` tại đúng source edge.

## NAT evidence

Lab đang render không có `masquerade` hoặc `snat` vì source of truth có route
hai chiều. Không được kết luận chỉ bằng thiết kế. Runtime checker chỉ in:

```text
NAT NOT REQUIRED AND RUNTIME PROVEN
```

khi đồng thời có route live, không có NAT rule và `tcpdump` tại `hcall` thấy
nguyên source IP của `h20_01`. Nếu thiếu một bằng chứng, kết luận phải là:

```text
NAT REQUIREMENT NOT YET CONCLUDED
```

## Error scan

```bash
grep -RniE 'Traceback|Exception|BrokenPipeError|Connection refused|nft syntax error|rule apply failure|namespace missing|route missing|duplicate rule|FAILED|CRITICAL' \
  sdn_mpls_demo/runtime runtime_reports || true
```

Cảnh báo Eventlet `RLock(s) were not greened` chỉ được ghi non-blocking khi
controller, 9 OVS, OpenFlow và toàn bộ firewall checkpoint đều PASS.

