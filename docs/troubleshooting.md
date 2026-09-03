# Xử lý sự cố

## Port

```bash
ss -ltnp | grep -E ':(6653|8000|5173)([[:space:]]|$)'
```

Port mở chưa đủ kết luận healthy; kiểm tra process owner và `/api/health`.

## 6 OVS không connected

```bash
sudo ovs-vsctl show
tail -n 100 sdn_mpls_demo/runtime/controller.log
```

Inventory đúng: `access_floor1`, `access_floor2`, `core_hq`, `access_branch`, `dist_branch`, `infra_access`. Tất cả phải trỏ tới `tcp:127.0.0.1:6653` và `is_connected=true`.

## Thiếu pipeline

```bash
for table in 0 10 20 30; do
  sudo ovs-ofctl -O OpenFlow13 dump-flows access_floor1 "table=$table"
done
```

Nếu thiếu flow, kiểm tra controller log, port inventory và source-of-truth validation.

## Control agent/socket

```bash
ls -l /tmp/cch_mininet_control.sock
./scripts/check_demo_health.sh
```

Socket tồn tại nhưng HEALTH không trả `agent_alive=true` là stale/not ready, không phải PASS.

## Dashboard

```bash
tail -n 100 logs/backend.log
tail -n 100 logs/frontend.log
curl -fsS http://127.0.0.1:8000/api/health
```

Không đưa traceback/token ra UI. Dùng request ID để đối chiếu log.

## Cleanup

```bash
./scripts/stop_demo.sh
sudo mn -c
```
