#!/usr/bin/env bash
set -e

cd /home/huy/CCH_Network
mkdir -p logs
echo "Starting Mininet topology..."
sudo mn -c || true
export CCH_DAEMON=1
nohup sudo -E ./sdn_mpls_demo/run_topology.sh > logs/topology.log 2>&1 &
echo "Launched topology, waiting for Mininet nodes..."

for i in $(seq 1 30); do
  if pgrep -f "mininet:core_hq" >/dev/null 2>&1; then
    echo "Mininet core_hq node is UP!"
    break
  fi
  sleep 1
done

sleep 3
ps aux | grep mininet | head -n 20
