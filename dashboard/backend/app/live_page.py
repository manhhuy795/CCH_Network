from __future__ import annotations


LIVE_DASHBOARD_HTML = """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CCH SDN Live Dashboard</title>
  <style>
    :root { color: #172033; background: #edf2f6; font-family: Inter, system-ui, -apple-system, Segoe UI, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; }
    main { min-height: 100vh; padding: 18px; }
    header, section { background: #fff; border: 1px solid #dbe3ec; border-radius: 8px; box-shadow: 0 12px 28px rgba(23,32,51,.06); }
    header { align-items: center; display: flex; justify-content: space-between; gap: 16px; margin-bottom: 14px; padding: 16px 18px; }
    h1 { font-size: 24px; line-height: 1.2; margin: 0 0 4px; }
    h2 { font-size: 16px; margin: 0; }
    h3 { font-size: 14px; margin: 0 0 8px; }
    p { color: #5f6f82; margin: 0; }
    .grid { display: grid; gap: 14px; grid-template-columns: minmax(0, 1fr) 410px; }
    .panel { overflow: hidden; }
    .panel-head { align-items: center; background: #fbfcfe; border-bottom: 1px solid #e3e8ef; display: flex; justify-content: space-between; min-height: 48px; padding: 11px 14px; }
    .content { padding: 14px; }
    .cards { display: grid; gap: 10px; grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .card { border: 1px solid #e2e8f0; border-left: 4px solid #176b55; border-radius: 8px; min-height: 74px; padding: 10px; }
    .card:nth-child(2) { border-left-color: #5b52b8; }
    .card:nth-child(3) { border-left-color: #c77a1b; }
    .card:nth-child(4) { border-left-color: #b23b30; }
    .card strong { display: block; font-size: 21px; }
    .card span { color: #66758a; font-size: 12px; }
    .description { display: grid; gap: 10px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .description div { background: #f8fafc; border: 1px solid #e4eaf1; border-radius: 8px; padding: 12px; }
    .description p { font-size: 13px; line-height: 1.45; }
    label { color: #5d6b7d; display: grid; font-size: 12px; gap: 6px; }
    select, input { background: #fff; border: 1px solid #ccd6e2; border-radius: 7px; min-height: 38px; padding: 7px 9px; width: 100%; }
    .form { display: grid; gap: 12px; grid-template-columns: 1fr 1fr; }
    .buttons { display: grid; gap: 8px; grid-template-columns: 1fr 1fr; margin-top: 12px; }
    button { background: #fff; border: 1px solid #cfd8e3; border-radius: 7px; color: #172033; cursor: pointer; min-height: 38px; padding: 8px 12px; }
    button:hover { border-color: #7a8ba3; box-shadow: 0 6px 16px rgba(23,32,51,.08); }
    .primary { background: #176b55; border-color: #176b55; color: #fff; }
    .danger { border-color: #f0b4ac; color: #9f3328; }
    .wide { grid-column: 1 / -1; }
    .result { border-left: 4px solid #5b52b8; background: #f8fafc; border-radius: 8px; margin-top: 12px; min-height: 78px; padding: 12px; }
    .result.ok { border-left-color: #176b55; }
    .result.bad { border-left-color: #b23b30; }
    .result strong { display: block; font-size: 15px; margin-bottom: 5px; }
    pre { background: #101827; border-radius: 8px; color: #d7e2f0; font-size: 13px; line-height: 1.45; margin: 0; max-height: 420px; overflow: auto; padding: 14px; white-space: pre-wrap; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border-bottom: 1px solid #edf2f7; font-size: 13px; padding: 8px; text-align: left; vertical-align: top; }
    th { background: #f6f8fb; color: #516174; position: sticky; top: 0; }
    .table-wrap { max-height: 390px; overflow: auto; }
    .badge { border-radius: 999px; display: inline-block; font-size: 12px; font-weight: 700; min-width: 62px; padding: 4px 9px; text-align: center; }
    .badge.allow { background: #dff6ea; color: #176b55; }
    .badge.drop { background: #fde6e3; color: #a33428; }
    .topology-wrap { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }
    svg { display: block; width: 100%; height: auto; }
    .zone { fill: #eef4f8; stroke: #d5e0ea; }
    .zone-label { fill: #64748b; font-size: 12px; font-weight: 700; letter-spacing: .04em; }
    .node rect { fill: #fff; stroke: #cbd5e1; stroke-width: 1.4; rx: 7; }
    .node.service rect { stroke: #a6dcc2; stroke-width: 2; }
    .node.blocked rect { stroke: #efb6ae; stroke-width: 2; }
    .node.switch rect { stroke: #5b52b8; stroke-width: 2; }
    .node text { fill: #172033; font-size: 12px; font-weight: 700; }
    .node .sub { fill: #64748b; font-size: 10px; font-weight: 500; }
    .link { stroke: #66758a; stroke-width: 2.2; marker-end: url(#arrow); }
    .link.active { stroke: #176b55; stroke-width: 4; marker-end: url(#arrowActive); }
    .link.blocked { stroke: #b23b30; stroke-dasharray: 7 5; stroke-width: 4; marker-end: url(#arrowBlocked); }
    .packet { fill: #176b55; opacity: 0; }
    .packet.active { opacity: 1; animation: pulse 1s ease-in-out infinite; }
    .xmark { display: none; }
    .xmark.show line { stroke: #b23b30; stroke-width: 6; stroke-linecap: round; }
    .xmark.show { display: block; }
    @keyframes pulse { 0%,100% { r: 6; opacity: .55; } 50% { r: 10; opacity: 1; } }
    @media (max-width: 1100px) { .grid, .cards, .description, .form, .buttons { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>CCH SDN Live Dashboard</h1>
      <p>Dieu khien policy, ping, bandwidth va OpenFlow tren Mininet + Open vSwitch dang chay.</p>
    </div>
    <button class="primary" onclick="refreshAll()">Refresh</button>
  </header>

  <section class="panel" style="margin-bottom:14px">
    <div class="panel-head"><h2>Mo ta he thong</h2><span id="liveStatus">checking...</span></div>
    <div class="content description">
      <div><h3>Data plane</h3><p>Mininet tao cac host h20/h30/h40/h50/h60 va service h90/hzalo/hcall/hsocial. Open vSwitch s1 chuyen goi theo flow.</p></div>
      <div><h3>Control plane</h3><p>Controller Python doc policy trong sdn_demo/policy.yml va cai flow allow/drop xuong OVS bang OpenFlow 1.3.</p></div>
      <div><h3>Management plane</h3><p>Web nay goi lenh that vao namespace Mininet de ping, do iperf, block/unblock va doc counter flow.</p></div>
    </div>
  </section>

  <section class="panel" style="margin-bottom:14px">
    <div class="panel-head"><h2>Trang thai live</h2><span>real Mininet/OVS</span></div>
    <div class="content cards">
      <div class="card"><strong id="hostCount">0</strong><span>Mininet hosts found</span></div>
      <div class="card"><strong id="flowCount">0</strong><span>OpenFlow rules</span></div>
      <div class="card"><strong id="byteCount">0</strong><span>Flow bytes</span></div>
      <div class="card"><strong id="lastDecision">READY</strong><span>Last ping decision</span></div>
    </div>
  </section>

  <div class="grid">
    <div>
      <section class="panel">
        <div class="panel-head"><h2>So do mang SDN</h2><span>duong thang, ngang, cheo</span></div>
        <div class="content">
          <div class="topology-wrap">
            <svg viewBox="0 0 1040 520" role="img" aria-label="SDN topology">
              <defs>
                <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#66758a"/></marker>
                <marker id="arrowActive" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#176b55"/></marker>
                <marker id="arrowBlocked" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#b23b30"/></marker>
              </defs>
              <rect class="zone" x="18" y="48" width="250" height="290" rx="8"/>
              <text class="zone-label" x="34" y="72">HQ USERS</text>
              <rect class="zone" x="18" y="360" width="250" height="130" rx="8"/>
              <text class="zone-label" x="34" y="384">BRANCH USERS</text>
              <rect class="zone" x="774" y="48" width="246" height="442" rx="8"/>
              <text class="zone-label" x="790" y="72">SERVICE ZONE</text>

              <line id="link-h20-s1" class="link" x1="168" y1="112" x2="470" y2="250"/>
              <line id="link-h30-s1" class="link" x1="168" y1="192" x2="470" y2="250"/>
              <line id="link-h40-s1" class="link" x1="168" y1="272" x2="470" y2="250"/>
              <line id="link-h50-s1" class="link" x1="168" y1="414" x2="470" y2="250"/>
              <line id="link-h60-s1" class="link" x1="168" y1="464" x2="470" y2="250"/>
              <line id="link-s1-h90" class="link" x1="570" y1="250" x2="880" y2="112"/>
              <line id="link-s1-hzalo" class="link" x1="570" y1="250" x2="880" y2="192"/>
              <line id="link-s1-hcall" class="link" x1="570" y1="250" x2="880" y2="272"/>
              <line id="link-s1-hsocial" class="link" x1="570" y1="250" x2="880" y2="352"/>

              <g id="node-h20" class="node"><rect x="38" y="92" width="130" height="42"/><text x="52" y="112">h20 Project A</text><text class="sub" x="52" y="126">172.10.20.10</text></g>
              <g id="node-h30" class="node"><rect x="38" y="172" width="130" height="42"/><text x="52" y="192">h30 Project B</text><text class="sub" x="52" y="206">172.10.30.10</text></g>
              <g id="node-h40" class="node"><rect x="38" y="252" width="130" height="42"/><text x="52" y="272">h40 Project C</text><text class="sub" x="52" y="286">172.10.40.10</text></g>
              <g id="node-h50" class="node"><rect x="38" y="394" width="130" height="42"/><text x="52" y="414">h50 Telesale</text><text class="sub" x="52" y="428">172.10.50.10</text></g>
              <g id="node-h60" class="node"><rect x="38" y="444" width="130" height="42"/><text x="52" y="464">h60 Admin</text><text class="sub" x="52" y="478">172.10.60.10</text></g>
              <g id="node-s1" class="node switch"><rect x="470" y="222" width="100" height="56"/><text x="492" y="248">s1 OVS</text><text class="sub" x="486" y="264">OpenFlow13</text></g>
              <g id="node-h90" class="node service"><rect x="880" y="92" width="124" height="42"/><text x="894" y="112">h90 Voice</text><text class="sub" x="894" y="126">172.10.90.10</text></g>
              <g id="node-hzalo" class="node service"><rect x="880" y="172" width="124" height="42"/><text x="894" y="192">hzalo</text><text class="sub" x="894" y="206">172.10.200.10</text></g>
              <g id="node-hcall" class="node service"><rect x="880" y="252" width="124" height="42"/><text x="894" y="272">hcall</text><text class="sub" x="894" y="286">172.10.201.10</text></g>
              <g id="node-hsocial" class="node blocked"><rect x="880" y="332" width="124" height="42"/><text x="894" y="352">hsocial</text><text class="sub" x="894" y="366">172.10.202.10</text></g>
              <circle id="packetDot" class="packet" cx="520" cy="250" r="7"/>
              <g id="xmark" class="xmark"><line x1="944" y1="398" x2="980" y2="434"/><line x1="980" y1="398" x2="944" y2="434"/></g>
            </svg>
          </div>
        </div>
      </section>

      <section class="panel" style="margin-top:14px">
        <div class="panel-head"><h2>OpenFlow flows da dich</h2><button onclick="loadFlows()">Load flows</button></div>
        <div class="content table-wrap">
          <table>
            <thead><tr><th>Y nghia rule</th><th>Match</th><th>Action</th><th>Priority</th><th>Counter</th><th>Raw action</th></tr></thead>
            <tbody id="flowRows"></tbody>
          </table>
        </div>
      </section>
    </div>

    <div>
      <section class="panel">
        <div class="panel-head"><h2>Test & Control</h2><span>live Mininet</span></div>
        <div class="content">
          <div class="form">
            <label>Source<select id="source"></select></label>
            <label>Destination<select id="destination"></select></label>
            <label class="wide">Seconds<input id="seconds" type="number" min="1" max="60" value="5" /></label>
          </div>
          <div class="buttons">
            <button class="primary" onclick="runPing()">Ping that</button>
            <button class="primary" onclick="runIperf('tcp')">Do bandwidth TCP</button>
            <button onclick="runIperf('udp')">Do bandwidth UDP</button>
            <button onclick="loadFlows()">Xem flow OVS</button>
            <button class="danger" onclick="blockPair()">Block bang OpenFlow</button>
            <button onclick="unblockPair()">Unblock</button>
          </div>
          <div id="result" class="result">
            <strong>San sang</strong>
            <p>Chon source/destination roi bam Ping hoac Iperf.</p>
          </div>
        </div>
      </section>

      <section class="panel" style="margin-top:14px">
        <div class="panel-head"><h2>Output that</h2><span id="lastAction">ready</span></div>
        <div class="content"><pre id="output">Ket qua Mininet/OVS se hien o day.</pre></div>
      </section>
    </div>
  </div>
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

const xPositions = {
  h20: [168, 112], h30: [168, 192], h40: [168, 272], h50: [168, 414], h60: [168, 464],
  h90: [880, 112], hzalo: [880, 192], hcall: [880, 272], hsocial: [880, 352],
};

function lineId(a, b) {
  return document.getElementById(`link-${a}-${b}`) ? `link-${a}-${b}` : `link-${b}-${a}`;
}

function clearPath() {
  document.querySelectorAll('.link').forEach((line) => line.classList.remove('active', 'blocked'));
  document.getElementById('packetDot').classList.remove('active');
  document.getElementById('xmark').classList.remove('show');
}

function drawDecision(payload) {
  clearPath();
  const decision = payload.decision || {};
  const path = decision.path || [];
  const blocked = decision.action === 'deny' || payload.ok === false;
  for (let i = 0; i < path.length - 1; i += 1) {
    const link = document.getElementById(lineId(path[i], path[i + 1]));
    if (link) link.classList.add(blocked ? 'blocked' : 'active');
  }
  const packet = document.getElementById('packetDot');
  const dst = path[path.length - 1];
  if (xPositions[dst]) {
    packet.setAttribute('cx', xPositions[dst][0]);
    packet.setAttribute('cy', xPositions[dst][1]);
  }
  packet.classList.add('active');
  if (blocked && xPositions[dst]) {
    const xmark = document.getElementById('xmark');
    const [x, y] = xPositions[dst];
    xmark.querySelectorAll('line')[0].setAttribute('x1', x + 18);
    xmark.querySelectorAll('line')[0].setAttribute('y1', y + 18);
    xmark.querySelectorAll('line')[0].setAttribute('x2', x + 50);
    xmark.querySelectorAll('line')[0].setAttribute('y2', y + 50);
    xmark.querySelectorAll('line')[1].setAttribute('x1', x + 50);
    xmark.querySelectorAll('line')[1].setAttribute('y1', y + 18);
    xmark.querySelectorAll('line')[1].setAttribute('x2', x + 18);
    xmark.querySelectorAll('line')[1].setAttribute('y2', y + 50);
    xmark.classList.add('show');
  }
}

function show(title, payload) {
  document.getElementById('lastAction').textContent = title;
  const raw = payload.raw || payload.result?.raw || JSON.stringify(payload, null, 2);
  document.getElementById('output').textContent = `${payload.message || title}\\n\\n${raw}`;
  const result = document.getElementById('result');
  result.className = `result ${payload.ok ? 'ok' : 'bad'}`;
  result.innerHTML = `<strong>${payload.message || title}</strong><p>${payload.decision?.reason || 'Ket qua duoc lay truc tiep tu Mininet/OVS.'}</p>`;
  document.getElementById('lastDecision').textContent = payload.ok ? 'ALLOW' : 'DENY';
}

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
      <td>${flow.explanation || flow.reason}</td>
      <td>${flow.match || (flow.src + ' -> ' + flow.dst)}</td>
      <td><span class="badge ${flow.action === 'ALLOW' ? 'allow' : 'drop'}">${flow.action}</span></td>
      <td>${flow.priority}</td>
      <td>${flow.packets} packets<br>${flow.bytes} bytes</td>
      <td>${flow.reason}</td>
    </tr>
  `).join('');
  document.getElementById('flowCount').textContent = (payload.flows || []).length;
  document.getElementById('byteCount').textContent = (payload.flows || []).reduce((sum, flow) => sum + (flow.bytes || 0), 0);
  if (!payload.flows?.length) show('OpenFlow flows', payload);
}

async function runPing() {
  show('Ping dang chay...', { ok: true, raw: 'Dang goi ping trong namespace Mininet...' });
  const payload = await post('/api/test/ping', selectedPair());
  drawDecision(payload);
  show(payload.ok ? 'Ping thanh cong' : 'Ping that bai', payload);
  await loadFlows();
}

async function runIperf(protocol) {
  const body = { ...selectedPair(), protocol, seconds: Number(document.getElementById('seconds').value || 5) };
  show('Iperf dang chay...', { ok: true, raw: 'Dang start iperf server va client trong namespace Mininet...' });
  const payload = await post('/api/test/iperf', body);
  drawDecision(payload);
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

refreshAll().catch((error) => show('Loi dashboard', { ok: false, raw: error.message }));
</script>
</body>
</html>
"""
