from __future__ import annotations


LIVE_DASHBOARD_HTML = """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CCH SDN Live Dashboard</title>
  <style>
    :root { color: #172033; background: #eef2f6; font-family: Inter, system-ui, -apple-system, Segoe UI, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; }
    main { min-height: 100vh; padding: 18px; }
    header, section { background: #fff; border: 1px solid #dbe3ec; border-radius: 10px; box-shadow: 0 12px 28px rgba(23,32,51,.06); }
    header { align-items: center; display: flex; justify-content: space-between; gap: 16px; margin-bottom: 14px; padding: 16px 18px; }
    h1 { font-size: 24px; line-height: 1.2; margin: 0 0 4px; }
    h2 { font-size: 16px; margin: 0; }
    p { color: #5f6f82; margin: 0; }
    .grid { display: grid; gap: 14px; grid-template-columns: minmax(0, 1fr) 420px; }
    .panel { overflow: hidden; }
    .panel-head { align-items: center; background: #fbfcfe; border-bottom: 1px solid #e3e8ef; display: flex; justify-content: space-between; padding: 12px 14px; }
    .content { padding: 14px; }
    .cards { display: grid; gap: 10px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .card { border: 1px solid #e2e8f0; border-left: 4px solid #176b55; border-radius: 8px; min-height: 76px; padding: 11px; }
    .card:nth-child(2) { border-left-color: #5b52b8; }
    .card:nth-child(3) { border-left-color: #c77a1b; }
    .card strong { display: block; font-size: 22px; }
    .card span { color: #66758a; font-size: 12px; }
    label { color: #5d6b7d; display: grid; font-size: 12px; gap: 6px; }
    select, input { background: #fff; border: 1px solid #ccd6e2; border-radius: 7px; min-height: 38px; padding: 7px 9px; width: 100%; }
    .form { display: grid; gap: 12px; grid-template-columns: 1fr 1fr; }
    .buttons { display: grid; gap: 8px; grid-template-columns: 1fr 1fr; margin-top: 12px; }
    button { background: #fff; border: 1px solid #cfd8e3; border-radius: 7px; color: #172033; cursor: pointer; min-height: 38px; padding: 8px 12px; }
    button:hover { border-color: #7a8ba3; box-shadow: 0 6px 16px rgba(23,32,51,.08); }
    .primary { background: #176b55; border-color: #176b55; color: #fff; }
    .danger { border-color: #f0b4ac; color: #9f3328; }
    pre { background: #101827; border-radius: 8px; color: #d7e2f0; font-size: 13px; line-height: 1.45; margin: 0; max-height: 520px; overflow: auto; padding: 14px; white-space: pre-wrap; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border-bottom: 1px solid #edf2f7; font-size: 13px; padding: 8px; text-align: left; vertical-align: top; }
    th { background: #f6f8fb; color: #516174; }
    .ok { color: #176b55; font-weight: 700; }
    .bad { color: #b23b30; font-weight: 700; }
    .wide { grid-column: 1 / -1; }
    @media (max-width: 1000px) { .grid, .cards, .form, .buttons { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>CCH SDN Live Dashboard</h1>
      <p>Thao tac truc tiep voi Mininet + Open vSwitch. Ket qua ping/iperf/flow lay tu lab dang chay.</p>
    </div>
    <button class="primary" onclick="refreshAll()">Refresh</button>
  </header>

  <div class="grid">
    <div>
      <section class="panel">
        <div class="panel-head"><h2>Live Status</h2><span id="liveStatus">checking...</span></div>
        <div class="content cards">
          <div class="card"><strong id="hostCount">0</strong><span>Mininet hosts found</span></div>
          <div class="card"><strong id="flowCount">0</strong><span>OpenFlow rules</span></div>
          <div class="card"><strong id="byteCount">0</strong><span>Flow bytes</span></div>
        </div>
      </section>

      <section class="panel" style="margin-top:14px">
        <div class="panel-head"><h2>OpenFlow Table</h2><button onclick="loadFlows()">Load flows</button></div>
        <div class="content" style="overflow:auto">
          <table>
            <thead><tr><th>Switch</th><th>Src</th><th>Dst</th><th>Action</th><th>Priority</th><th>Packets</th><th>Bytes</th><th>Raw action</th></tr></thead>
            <tbody id="flowRows"></tbody>
          </table>
        </div>
      </section>
    </div>

    <section class="panel">
      <div class="panel-head"><h2>Test & Control</h2><span>live Mininet</span></div>
      <div class="content">
        <div class="form">
          <label>Source<select id="source"></select></label>
          <label>Destination<select id="destination"></select></label>
          <label class="wide">Seconds<input id="seconds" type="number" min="1" max="60" value="5" /></label>
        </div>
        <div class="buttons">
          <button class="primary" onclick="runPing()">Ping thật</button>
          <button class="primary" onclick="runIperf('tcp')">Đo bandwidth TCP</button>
          <button onclick="runIperf('udp')">Đo bandwidth UDP</button>
          <button onclick="loadFlows()">Xem flow OVS</button>
          <button class="danger" onclick="blockPair()">Block bằng OpenFlow</button>
          <button onclick="unblockPair()">Unblock</button>
        </div>
      </div>
    </section>
  </div>

  <section class="panel" style="margin-top:14px">
    <div class="panel-head"><h2>Output thật từ Mininet/OVS</h2><span id="lastAction">ready</span></div>
    <div class="content"><pre id="output">Bam Ping, Iperf hoac Load flows de xem ket qua that.</pre></div>
  </section>
</main>

<script>
const api = async (path, options = {}) => {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
};

const post = (path, body) => api(path, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

const selectedPair = () => ({
  source: document.getElementById('source').value,
  destination: document.getElementById('destination').value,
});

const show = (title, payload) => {
  document.getElementById('lastAction').textContent = title;
  const raw = payload.raw || payload.result?.raw || JSON.stringify(payload, null, 2);
  document.getElementById('output').textContent = `${payload.message || title}\\n\\n${raw}`;
};

async function loadTopology() {
  const topology = await api('/api/topology');
  const hosts = topology.nodes.filter((node) => node.id.startsWith('h'));
  for (const id of ['source', 'destination']) {
    const select = document.getElementById(id);
    select.innerHTML = hosts.map((host) => `<option value="${host.id}">${host.id} - ${host.label} - ${host.ip}</option>`).join('');
  }
  document.getElementById('source').value = 'h20';
  document.getElementById('destination').value = 'h90';
}

async function loadStatus() {
  const status = await api('/api/live/status');
  const found = Object.values(status.hosts || {}).filter(Boolean).length;
  document.getElementById('hostCount').textContent = found;
  document.getElementById('liveStatus').innerHTML = status.ovs_bridge ? '<span class="ok">OVS s1 online</span>' : '<span class="bad">OVS s1 offline</span>';
}

async function loadFlows() {
  const payload = await api('/api/flows');
  const rows = document.getElementById('flowRows');
  rows.innerHTML = (payload.flows || []).map((flow) => `
    <tr>
      <td>${flow.switch}</td><td>${flow.src}</td><td>${flow.dst}</td><td>${flow.action}</td>
      <td>${flow.priority}</td><td>${flow.packets}</td><td>${flow.bytes}</td><td>${flow.reason}</td>
    </tr>
  `).join('');
  document.getElementById('flowCount').textContent = (payload.flows || []).length;
  document.getElementById('byteCount').textContent = (payload.flows || []).reduce((sum, flow) => sum + (flow.bytes || 0), 0);
  show('OpenFlow flows', payload);
}

async function runPing() {
  show('Ping dang chay...', { raw: 'Dang goi ping trong namespace Mininet...' });
  const payload = await post('/api/test/ping', selectedPair());
  show(payload.ok ? 'Ping thanh cong' : 'Ping that bai', payload);
  await loadFlows();
}

async function runIperf(protocol) {
  const body = { ...selectedPair(), protocol, seconds: Number(document.getElementById('seconds').value || 5) };
  show('Iperf dang chay...', { raw: 'Dang start iperf server va client trong namespace Mininet...' });
  const payload = await post('/api/test/iperf', body);
  show(`Iperf ${protocol.toUpperCase()}`, payload);
  await loadFlows();
}

async function blockPair() {
  const payload = await post('/api/live/block', selectedPair());
  show('Block OpenFlow', payload);
  await loadFlows();
}

async function unblockPair() {
  const payload = await post('/api/live/unblock', selectedPair());
  show('Unblock OpenFlow', payload);
  await loadFlows();
}

async function refreshAll() {
  await loadTopology();
  await loadStatus();
  await loadFlows();
}

refreshAll().catch((error) => show('Loi dashboard', { raw: error.message }));
</script>
</body>
</html>
"""
