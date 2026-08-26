#!/usr/bin/env bash
set -e

echo "=== Stopping old controller ==="
pkill -f osken-manager || true
sleep 1

echo "=== Starting controller_fabric.py ==="
cd /home/huy/CCH_Network
mkdir -p sdn_mpls_demo/runtime
: > sdn_mpls_demo/runtime/controller.log

nohup ./sdn_mpls_demo/.venv/bin/osken-manager \
  --ofp-listen-host 127.0.0.1 \
  --ofp-tcp-listen-port 6653 \
  sdn_mpls_demo/controller_fabric.py >> sdn_mpls_demo/runtime/controller.log 2>&1 &

CONTROLLER_PID=$!
echo "Controller PID: $CONTROLLER_PID"

# Wait for controller port 6653
for i in $(seq 1 20); do
  if ss -H -ltn | grep -q ':6653'; then
    echo "Controller is LISTENING on port 6653!"
    break
  fi
  sleep 0.5
done

sleep 2
echo "=== Controller log head ==="
head -n 30 sdn_mpls_demo/runtime/controller.log || true

echo "=== Controller status ==="
ps aux | grep osken-manager | grep -v grep || true
