# X? l? s? c?

## Port

~~~bash
ss -ltnp | grep -E ':(6653|8000|5173)([[:space:]]|$)'
~~~

Port m? kh?ng ?? ?? k?t lu?n healthy. Ki?m tra /api/health v? process owner. Port 8000 m? nh?ng API sai l? PORT_CONFLICT ho?c BACKEND_UNHEALTHY.

## Agent ho?c socket stale

~~~bash
ls -l /tmp/cch_mininet_control.sock
sudo -E env LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1   bash scripts/phase46_automation_docs_gate.sh preflight --reuse-running --verbose
~~~

Socket t?n t?i nh?ng HEALTH kh?ng tr? agent_alive=true l? AGENT_STALE_SOCKET/AGENT_NOT_READY. Kh?ng x?a socket b?ng tay khi topology c?n ch?y.

## OVS/OpenFlow

~~~bash
sudo ovs-vsctl list-br
sudo ovs-ofctl -O OpenFlow13 dump-flows core_hq
sudo ovs-ofctl -O OpenFlow13 dump-flows dist_telesale
~~~

C?n ??ng 9 bridge runtime. N?u flow thi?u, ki?m tra controller.log, topology log v? controller port 6653.

## Backend

~~~bash
tail -n 100 logs/backend.log
curl -fsS http://127.0.0.1:8000/api/health
~~~

Kh?ng ??a traceback ra UI; d?ng correlation/request ID trong log backend. Token ch? ??c t? logs/operator.token v? kh?ng in ra.

## Test b? BLOCKED

BLOCKED ngh?a l? ch?a c? b?ng ch?ng h?p l?, kh?ng ph?i PASS. ??c summary.json v? NEXT_ACTION.md trong report, s?a ??ng dependency/runtime state r?i ch?y l?i mode nh? nh?t.
