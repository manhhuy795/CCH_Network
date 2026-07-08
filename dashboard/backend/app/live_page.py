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
    .topology-wrap { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; overflow: auto; }
    svg { display: block; min-width: 1300px; width: 100%; height: auto; }
    .overlay-path { fill: none; opacity: 0; pointer-events: none; stroke-linecap: round; stroke-linejoin: round; stroke-width: 8; }
    .overlay-path.active { opacity: .95; stroke: #10b981; marker-end: url(#arrowActive); filter: drop-shadow(0 0 5px rgba(16,185,129,.45)); }
    .overlay-path.blocked { opacity: .95; stroke: #dc2626; stroke-dasharray: 18 12; marker-end: url(#arrowBlocked); filter: drop-shadow(0 0 5px rgba(220,38,38,.38)); }
    .packet { fill: #10b981; opacity: 0; pointer-events: none; stroke: #fff; stroke-width: 3; }
    .packet.active { opacity: 1; animation: pulse 1s ease-in-out infinite; }
    .xmark { display: none; pointer-events: none; }
    .xmark.show line { stroke: #dc2626; stroke-width: 14; stroke-linecap: round; filter: drop-shadow(0 0 5px rgba(220,38,38,.45)); }
    .xmark.show { display: block; }
    @keyframes pulse { 0%,100% { r: 11; opacity: .68; } 50% { r: 17; opacity: 1; } }
    @media (max-width: 1100px) { .grid, .cards, .description, .form, .buttons { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>CCH SDN Live Dashboard</h1>
      <p>So do hien thi dung theo anh logic CCH, overlay duong ping/bandwidth lay tu Mininet + OVS.</p>
    </div>
    <button class="primary" onclick="refreshAll()">Refresh</button>
  </header>

  <section class="panel" style="margin-bottom:14px">
    <div class="panel-head"><h2>Mo ta he thong</h2><span id="liveStatus">checking...</span></div>
    <div class="content description">
      <div><h3>Endpoint/User</h3><p>User duoc nhom theo Project, VLAN va Site nhu so do logic CCH goc.</p></div>
      <div><h3>SDN Control</h3><p>Controller cai flow allow/drop xuong Open vSwitch bang OpenFlow 1.3.</p></div>
      <div><h3>Security/Internet</h3><p>Firewall va policy node the hien Allow Zalo/Call App, Block Social Media.</p></div>
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
        <div class="panel-head"><h2>So do logic CCH</h2><span>anh goc + overlay SDN live</span></div>
        <div class="content">
          <div class="topology-wrap">
            <svg viewBox="0 0 1806 1227" role="img" aria-label="CCH logical network diagram">
              <defs>
                <marker id="arrowActive" markerWidth="16" markerHeight="16" refX="14" refY="5" orient="auto"><path d="M0,0 L0,10 L15,5 z" fill="#10b981"/></marker>
                <marker id="arrowBlocked" markerWidth="16" markerHeight="16" refX="14" refY="5" orient="auto"><path d="M0,0 L0,10 L15,5 z" fill="#dc2626"/></marker>
              </defs>
              <image href="/assets/So_do_logic_CCH.png" x="0" y="0" width="1806" height="1227" preserveAspectRatio="xMidYMid meet"/>

              <path id="link-h20-access_hq_a" class="overlay-path" d="M220 132 L276 132"/>
              <path id="link-h30-access_hq_b" class="overlay-path" d="M220 210 L276 220"/>
              <path id="link-h40-access_hq_c" class="overlay-path" d="M220 296 L276 300"/>
              <path id="link-h90-voice_mgmt" class="overlay-path" d="M220 480 L276 452"/>
              <path id="link-access_hq_a-core_hq" class="overlay-path" d="M452 142 L510 142 L570 182"/>
              <path id="link-access_hq_b-core_hq" class="overlay-path" d="M452 222 L510 222 L570 222"/>
              <path id="link-access_hq_c-core_hq" class="overlay-path" d="M452 302 L510 302 L570 262"/>
              <path id="link-voice_mgmt-core_hq" class="overlay-path" d="M452 452 L510 452 L570 342"/>
              <path id="link-core_hq-fw_hq" class="overlay-path" d="M832 340 L890 340 L946 370"/>
              <path id="link-fw_hq-policy_hq" class="overlay-path" d="M1068 408 L1068 440"/>
              <path id="link-policy_hq-internet" class="overlay-path" d="M1190 478 L1508 478 L1508 776"/>
              <path id="link-h50-access_branch" class="overlay-path" d="M220 780 L248 780 L276 814"/>
              <path id="link-h60-access_branch" class="overlay-path" d="M220 875 L248 875 L276 838"/>
              <path id="link-access_branch-dist_branch" class="overlay-path" d="M462 835 L570 835"/>
              <path id="link-dist_branch-fw_branch" class="overlay-path" d="M842 928 L890 928 L946 916"/>
              <path id="link-fw_branch-policy_branch" class="overlay-path" d="M1068 958 L1068 1006"/>
              <path id="link-policy_branch-internet" class="overlay-path" d="M1190 1038 L1508 1038 L1508 936"/>
              <path id="link-core_hq-ce_hq" class="overlay-path" d="M832 220 L890 220 L946 180"/>
              <path id="link-ce_hq-mpls_cloud" class="overlay-path" d="M1190 180 L1338 180 L1604 204"/>
              <path id="link-dist_branch-ce_branch" class="overlay-path" d="M842 748 L890 748 L946 748"/>
              <path id="link-ce_branch-mpls_cloud" class="overlay-path" d="M1190 748 L1458 748 L1604 632"/>
              <path id="link-internet-hzalo" class="overlay-path" d="M1510 776 L1510 478"/>
              <path id="link-internet-hcall" class="overlay-path" d="M1510 776 L1510 478"/>
              <path id="link-internet-hsocial" class="overlay-path" d="M1510 776 L1510 1038"/>

              <circle id="packetDot" class="packet" cx="570" cy="220" r="12"/>
              <g id="xmark" class="xmark"><line x1="1510" y1="1020" x2="1562" y2="1072"/><line x1="1562" y1="1020" x2="1510" y2="1072"/></g>
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

const nodePositions = {
  h20: [220, 132], h30: [220, 210], h40: [220, 296], h90: [220, 480],
  access_hq_a: [452, 142], access_hq_b: [452, 222], access_hq_c: [452, 302], voice_mgmt: [452, 452],
  core_hq: [832, 260], ce_hq: [1190, 180], fw_hq: [1190, 370], policy_hq: [1190, 478],
  h50: [220, 780], h60: [220, 875], access_branch: [462, 835], dist_branch: [842, 835],
  ce_branch: [1190, 748], fw_branch: [1190, 916], policy_branch: [1190, 1038],
  mpls_cloud: [1604, 430], internet: [1510, 820], hzalo: [1510, 478], hcall: [1510, 478], hsocial: [1510, 1038],
};

function lineId(a, b) {
  return document.getElementById(`link-${a}-${b}`) ? `link-${a}-${b}` : `link-${b}-${a}`;
}

function clearPath() {
  document.querySelectorAll('.overlay-path').forEach((line) => line.classList.remove('active', 'blocked'));
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
  if (nodePositions[dst]) {
    packet.setAttribute('cx', nodePositions[dst][0]);
    packet.setAttribute('cy', nodePositions[dst][1]);
  }
  packet.classList.add('active');
  if (blocked && nodePositions[dst]) {
    const xmark = document.getElementById('xmark');
    const [x, y] = nodePositions[dst];
    xmark.querySelectorAll('line')[0].setAttribute('x1', x + 18);
    xmark.querySelectorAll('line')[0].setAttribute('y1', y + 18);
    xmark.querySelectorAll('line')[0].setAttribute('x2', x + 70);
    xmark.querySelectorAll('line')[0].setAttribute('y2', y + 70);
    xmark.querySelectorAll('line')[1].setAttribute('x1', x + 70);
    xmark.querySelectorAll('line')[1].setAttribute('y1', y + 18);
    xmark.querySelectorAll('line')[1].setAttribute('x2', x + 18);
    xmark.querySelectorAll('line')[1].setAttribute('y2', y + 70);
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
    select.innerHTML = hosts.map((host) => `<option value="${host.id}">${host.label} (${host.id}) - ${host.ip}</option>`).join('');
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
