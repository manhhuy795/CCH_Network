# Phase 43 - Ubuntu OpenFlow Live Validation

Chỉ đánh dấu Phase 43 PASS sau khi chạy thật trên Ubuntu với Mininet, Open
vSwitch và OS-Ken. Branch dùng để kiểm tra là `transfer/phase43-candidate`.

## Terminal 1 - topology

```bash
cd ~/Downloads/CCH_Network
git fetch origin
git switch transfer/phase43-candidate
git pull --ff-only origin transfer/phase43-candidate
git branch --show-current
git rev-parse --short HEAD
git status --short

sudo mn -c
CCH_AUTO_TEST_POLICY=0 sudo -E ./sdn_mpls_demo/run_topology.sh
```

Giữ Terminal 1 tại prompt `mininet>`.

## Terminal 2 - inventory và controller connection

```bash
cd ~/Downloads/CCH_Network
sudo ovs-vsctl show
sudo ovs-vsctl list-br

for br in \
  access_hq_a access_hq_b access_hq_c access_bo access_hq_it \
  voice_access core_hq access_telesale dist_telesale
do
  controller_uuid="$(sudo ovs-vsctl --data=bare --no-heading get Bridge "$br" controller | tr -d '[]')"
  printf '%-22s controller=' "$br"
  sudo ovs-vsctl --data=bare --no-heading get Controller "$controller_uuid" target
  printf '%-22s connected=' "$br"
  sudo ovs-vsctl --data=bare --no-heading get Controller "$controller_uuid" is_connected
done
```

Kỳ vọng đúng 9 bridge trên dùng `tcp:127.0.0.1:6653` và `is_connected=true`.
`access_bo` là runtime bridge của logical ID `access_backoffice`, không phải OVS
thứ 10.

Chứng minh node ngoài OpenFlow domain không phải OVS controller target:

```bash
for node in service_net ce_hq ce_telesale fw_hq fw_telesale mpls_cloud internet_zone
do
  if sudo ovs-vsctl br-exists "$node"; then
    echo "FAIL unexpected OVS bridge: $node"
  else
    echo "PASS non-controller node: $node"
  fi
done
```

## Flow placement và counter

Trước traffic:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows core_hq | tee /tmp/core-before.txt
sudo ovs-ofctl -O OpenFlow13 dump-flows dist_telesale | tee /tmp/telesale-before.txt
sudo ovs-ofctl -O OpenFlow13 dump-flows access_bo | tee /tmp/access-bo.txt

grep 'cookie=0x1002' /tmp/core-before.txt
grep 'cookie=0x1002' /tmp/telesale-before.txt
```

Tại Terminal 1:

```text
h50_01 ping -c 3 h60_01
h60_01 ping -c 3 h50_01
h60_01 ping -c 3 h90
h50_01 ping -c 3 h90
```

Kỳ vọng:

- `h50_01 -> h60_01`: DENY tại `dist_telesale`.
- `h60_01 -> h50_01`: DENY tại `core_hq`.
- `h60_01 -> h90`: ALLOW theo path local HQ, không qua CE/MPLS/firewall.
- `h50_01 -> h90`: ALLOW qua CE/MPLS, không qua firewall Internet.

Sau traffic:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows core_hq | tee /tmp/core-after.txt
sudo ovs-ofctl -O OpenFlow13 dump-flows dist_telesale | tee /tmp/telesale-after.txt

grep 'cookie=0x1002' /tmp/core-after.txt
grep 'cookie=0x1002' /tmp/telesale-after.txt
```

Đối chiếu flow `cookie=0x1002, priority=400, actions=drop`. Packet counter của
flow đúng hướng phải tăng sau ping. Flow Telesale -> BackOffice chỉ ở
`dist_telesale`; flow BackOffice -> Telesale chỉ ở `core_hq`.

## Reload policy

```bash
cd ~/Downloads/CCH_Network
sudo -E .venv/bin/python - <<'PY'
import json
import os
import socket

request = {
    "token": os.environ.get("CCH_OSKEN_ADMIN_TOKEN", "cch-local-admin-token"),
    "action": "reload_policy",
}
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.connect(os.environ.get("CCH_OSKEN_ADMIN_SOCKET", "/tmp/cch_osken_admin.sock"))
    client.sendall(json.dumps(request).encode("utf-8"))
    print(client.recv(65536).decode("utf-8"))
PY

sudo ovs-ofctl -O OpenFlow13 dump-flows core_hq | grep 'cookie=0x1002'
sudo ovs-ofctl -O OpenFlow13 dump-flows dist_telesale | grep 'cookie=0x1002'
```

Kỳ vọng response `ok: true`; mỗi `(cookie, priority, match, action)` chỉ xuất
hiện một lần trên switch được chỉ định.

## Full policy runtime test

Tại Terminal 1:

```text
testpolicy
```

Lưu raw output sau:

- branch, HEAD và `git status --short`;
- `ovs-vsctl show`, `list-br`, controller target/connection của 9 OVS;
- ba flow dump ban đầu;
- bốn kết quả ping;
- flow dump và packet counter trước/sau;
- response reload và flow dump sau reload;
- toàn bộ bảng `testpolicy`;
- `sdn_mpls_demo/runtime/controller.log` nếu có FAIL.
