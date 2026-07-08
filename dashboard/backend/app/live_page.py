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
    .topology-wrap { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; overflow: auto; }
    svg { display: block; min-width: 1180px; width: 100%; height: auto; }
    .layer { fill: #f2f4f7; stroke: #9aa8b8; }
    .layer-text { fill: #26344a; font-size: 12px; font-weight: 800; }
    .site { fill: transparent; stroke: #9aa8b8; stroke-width: 1.2; }
    .site-title { fill: #172033; font-size: 13px; font-weight: 800; }
    .node rect { fill: #fff; stroke: #cbd5e1; stroke-width: 1.4; rx: 3; }
    .node.user rect { fill: #d9e8ff; stroke: #7aa0dc; }
    .node.access rect { fill: #dff0d8; stroke: #77ad65; }
    .node.core rect, .node.dist rect { fill: #ffe8c8; stroke: #efa221; }
    .node.ce rect { fill: #e4d7ef; stroke: #9a7bb7; }
    .node.firewall rect { fill: #f8cfcc; stroke: #df7770; }
    .node.policy rect { fill: #ffd99d; stroke: #e19424; }
    .node.service rect { fill: #e8f7ee; stroke: #6fbd8d; }
    .node.blocked rect { fill: #ffe8e5; stroke: #df7770; }
    .node.cloud ellipse { fill: #fff0bf; stroke: #dda935; stroke-width: 1.4; }
    .node text { fill: #172033; font-size: 11px; font-weight: 700; text-anchor: middle; }
    .node .sub { fill: #435267; font-size: 9.5px; font-weight: 500; }
    .link { stroke: #2f3642; stroke-width: 2; marker-end: url(#arrow); }
    .link.policy-link { stroke-dasharray: 7 6; }
    .link.static { stroke: #8b95a3; stroke-width: 1.6; }
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
      <p>So do logic theo Site/VLAN/Layer, ket qua ping va bandwidth lay truc tiep tu Mininet + OVS.</p>
    </div>
    <button class="primary" onclick="refreshAll()">Refresh</button>
  </header>

  <section class="panel" style="margin-bottom:14px">
    <div class="panel-head"><h2>Mo ta he thong</h2><span id="liveStatus">checking...</span></div>
    <div class="content description">
      <div><h3>Endpoint/User</h3><p>User duoc nhom theo Project, VLAN va Site de de lien he voi so do logic CCH.</p></div>
      <div><h3>SDN Control</h3><p>Controller doc policy va cai flow allow/drop xuong Open vSwitch bang OpenFlow 1.3.</p></div>
      <div><h3>Security/Internet</h3><p>Firewall va policy node the hien logic Allow Zalo/Call App, Block Social Media.</p></div>
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
        <div class="panel-head"><h2>So do logic CCH - SDN view</h2><span>Endpoint -> Access -> Core/Distribution -> WAN/Security -> Internet</span></div>
        <div class="content">
          <div class="topology-wrap">
            <svg viewBox="0 0 1180 720" role="img" aria-label="CCH logical SDN topology">
              <defs>
                <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#2f3642"/></marker>
                <marker id="arrowActive" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#176b55"/></marker>
                <marker id="arrowBlocked" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#b23b30"/></marker>
              </defs>

              <rect class="layer" x="18" y="8" width="140" height="28"/><text class="layer-text" x="88" y="27" text-anchor="middle">ENDPOINT / USER</text>
              <rect class="layer" x="206" y="8" width="140" height="28"/><text class="layer-text" x="276" y="27" text-anchor="middle">ACCESS LAYER</text>
              <rect class="layer" x="410" y="8" width="190" height="28"/><text class="layer-text" x="505" y="27" text-anchor="middle">CORE / DISTRIBUTION</text>
              <rect class="layer" x="670" y="8" width="210" height="28"/><text class="layer-text" x="775" y="27" text-anchor="middle">WAN / SECURITY EDGE</text>
              <rect class="layer" x="974" y="8" width="170" height="28"/><text class="layer-text" x="1059" y="27" text-anchor="middle">ISP / INTERNET</text>

              <rect class="site" x="10" y="52" width="900" height="330"/><text class="site-title" x="460" y="74" text-anchor="middle">SITE CHINH - TRU SO</text>
              <rect class="site" x="10" y="408" width="900" height="270"/><text class="site-title" x="460" y="430" text-anchor="middle">SITE CHI NHANH - TELESALE</text>

              <line id="link-h20-access_hq_a" class="link" x1="150" y1="112" x2="224" y2="112"/>
              <line id="link-h30-access_hq_b" class="link" x1="150" y1="170" x2="224" y2="170"/>
              <line id="link-h40-access_hq_c" class="link" x1="150" y1="228" x2="224" y2="228"/>
              <line id="link-h90-voice_mgmt" class="link" x1="150" y1="322" x2="224" y2="322"/>
              <line id="link-access_hq_a-core_hq" class="link" x1="340" y1="112" x2="438" y2="180"/>
              <line id="link-access_hq_b-core_hq" class="link" x1="340" y1="170" x2="438" y2="205"/>
              <line id="link-access_hq_c-core_hq" class="link" x1="340" y1="228" x2="438" y2="230"/>
              <line id="link-voice_mgmt-core_hq" class="link" x1="340" y1="322" x2="438" y2="250"/>
              <line id="link-core_hq-fw_hq" class="link" x1="590" y1="220" x2="692" y2="220"/>
              <line id="link-fw_hq-policy_hq" class="link policy-link" x1="775" y1="252" x2="775" y2="296"/>
              <line id="link-policy_hq-internet" class="link policy-link" x1="858" y1="316" x2="1012" y2="316"/>

              <line id="link-h50-access_branch" class="link" x1="150" y1="486" x2="224" y2="520"/>
              <line id="link-h60-access_branch" class="link" x1="150" y1="562" x2="224" y2="536"/>
              <line id="link-access_branch-dist_branch" class="link" x1="340" y1="528" x2="438" y2="528"/>
              <line id="link-dist_branch-fw_branch" class="link" x1="590" y1="528" x2="692" y2="528"/>
              <line id="link-fw_branch-policy_branch" class="link policy-link" x1="775" y1="560" x2="775" y2="604"/>
              <line id="link-policy_branch-internet" class="link policy-link" x1="858" y1="624" x2="1012" y2="422"/>

              <line id="link-core_hq-ce_hq" class="link static" x1="590" y1="180" x2="692" y2="128"/>
              <line id="link-ce_hq-mpls_cloud" class="link static" x1="858" y1="128" x2="1012" y2="210"/>
              <line id="link-dist_branch-ce_branch" class="link static" x1="590" y1="488" x2="692" y2="472"/>
              <line id="link-ce_branch-mpls_cloud" class="link static" x1="858" y1="472" x2="1012" y2="330"/>
              <line id="link-internet-hzalo" class="link" x1="1100" y1="350" x2="1100" y2="208"/>
              <line id="link-internet-hcall" class="link" x1="1100" y1="350" x2="1100" y2="270"/>
              <line id="link-internet-hsocial" class="link" x1="1100" y1="350" x2="1100" y2="560"/>

              <g id="node-h20" class="node user"><rect x="28" y="88" width="122" height="48"/><text x="89" y="106">Project A</text><text class="sub" x="89" y="121">VLAN 20 - HQ</text><text class="sub" x="89" y="133">172.10.20.0/24</text></g>
              <g id="node-h30" class="node user"><rect x="28" y="146" width="122" height="48"/><text x="89" y="164">Project B</text><text class="sub" x="89" y="179">VLAN 30 - HQ</text><text class="sub" x="89" y="191">172.10.30.0/24</text></g>
              <g id="node-h40" class="node user"><rect x="28" y="204" width="122" height="48"/><text x="89" y="222">Project C</text><text class="sub" x="89" y="237">VLAN 40 - HQ</text><text class="sub" x="89" y="249">172.10.40.0/24</text></g>
              <g id="node-h90" class="node user"><rect x="28" y="298" width="122" height="48"/><text x="89" y="316">Voice Service</text><text class="sub" x="89" y="331">VLAN 90 - HQ</text><text class="sub" x="89" y="343">172.10.90.0/24</text></g>

              <g id="node-access_hq_a" class="node access"><rect x="224" y="88" width="116" height="48"/><text x="282" y="108">Access SW A</text><text class="sub" x="282" y="124">VLAN 20</text></g>
              <g id="node-access_hq_b" class="node access"><rect x="224" y="146" width="116" height="48"/><text x="282" y="166">Access SW B</text><text class="sub" x="282" y="182">VLAN 30</text></g>
              <g id="node-access_hq_c" class="node access"><rect x="224" y="204" width="116" height="48"/><text x="282" y="224">Access SW C</text><text class="sub" x="282" y="240">VLAN 40</text></g>
              <g id="node-voice_mgmt" class="node access"><rect x="224" y="298" width="116" height="48"/><text x="282" y="316">Voice/Mgmt SW</text><text class="sub" x="282" y="331">VLAN 90</text></g>

              <g id="node-core_hq" class="node core"><rect x="438" y="154" width="152" height="132"/><text x="514" y="196">Core L3 - HQ</text><text class="sub" x="514" y="214">SVI GW VLAN</text><text class="sub" x="514" y="228">10/20/30/40/90</text><text class="sub" x="514" y="244">Default -> Firewall</text></g>
              <g id="node-ce_hq" class="node ce"><rect x="692" y="100" width="166" height="56"/><text x="775" y="122">CE Router HQ</text><text class="sub" x="775" y="138">MPLS WAN Edge</text></g>
              <g id="node-fw_hq" class="node firewall"><rect x="692" y="196" width="166" height="56"/><text x="775" y="218">Firewall HQ</text><text class="sub" x="775" y="234">Internet Breakout</text></g>
              <g id="node-policy_hq" class="node policy"><rect x="692" y="296" width="166" height="48"/><text x="775" y="314">Policy Internet HQ</text><text class="sub" x="775" y="330">Allow Zalo + Call App</text></g>

              <g id="node-h50" class="node user"><rect x="28" y="462" width="122" height="48"/><text x="89" y="480">Telesale</text><text class="sub" x="89" y="495">VLAN 50 - Branch</text><text class="sub" x="89" y="507">172.10.50.0/24</text></g>
              <g id="node-h60" class="node user"><rect x="28" y="538" width="122" height="48"/><text x="89" y="556">Backoffice</text><text class="sub" x="89" y="571">VLAN 60 - Branch</text><text class="sub" x="89" y="583">172.10.60.0/24</text></g>
              <g id="node-access_branch" class="node access"><rect x="224" y="500" width="116" height="56"/><text x="282" y="520">Access SW</text><text class="sub" x="282" y="536">VLAN 50/60</text></g>
              <g id="node-dist_branch" class="node dist"><rect x="438" y="478" width="152" height="100"/><text x="514" y="514">Distribution L3</text><text class="sub" x="514" y="532">Branch SVI GW</text><text class="sub" x="514" y="546">VLAN 50/60</text></g>
              <g id="node-ce_branch" class="node ce"><rect x="692" y="444" width="166" height="56"/><text x="775" y="466">CE Router Branch</text><text class="sub" x="775" y="482">MPLS WAN Edge</text></g>
              <g id="node-fw_branch" class="node firewall"><rect x="692" y="504" width="166" height="56"/><text x="775" y="526">Firewall Branch</text><text class="sub" x="775" y="542">Internet Breakout</text></g>
              <g id="node-policy_branch" class="node policy"><rect x="692" y="604" width="166" height="48"/><text x="775" y="622">Policy Internet Branch</text><text class="sub" x="775" y="638">Allow Zalo + Call App</text></g>

              <g id="node-mpls_cloud" class="node cloud"><ellipse cx="1058" cy="260" rx="86" ry="74"/><text x="1058" y="244">MPLS L3VPN</text><text class="sub" x="1058" y="262">ISP PE/P Core</text></g>
              <g id="node-internet" class="node cloud"><ellipse cx="1058" cy="408" rx="86" ry="62"/><text x="1058" y="412">Internet</text></g>
              <g id="node-hzalo" class="node service"><rect x="1038" y="184" width="116" height="48"/><text x="1096" y="204">Zalo Service</text><text class="sub" x="1096" y="220">172.10.200.10</text></g>
              <g id="node-hcall" class="node service"><rect x="1038" y="246" width="116" height="48"/><text x="1096" y="266">Call App</text><text class="sub" x="1096" y="282">172.10.201.10</text></g>
              <g id="node-hsocial" class="node blocked"><rect x="1038" y="536" width="116" height="48"/><text x="1096" y="556">Social Media</text><text class="sub" x="1096" y="572">Blocked</text></g>

              <circle id="packetDot" class="packet" cx="514" cy="220" r="7"/>
              <g id="xmark" class="xmark"><line x1="1078" y1="586" x2="1114" y2="622"/><line x1="1114" y1="586" x2="1078" y2="622"/></g>
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
  h20: [150, 112], h30: [150, 170], h40: [150, 228], h90: [150, 322],
  access_hq_a: [224, 112], access_hq_b: [224, 170], access_hq_c: [224, 228], voice_mgmt: [224, 322],
  core_hq: [514, 220], ce_hq: [775, 128], fw_hq: [775, 224], policy_hq: [775, 320],
  h50: [150, 486], h60: [150, 562], access_branch: [224, 528], dist_branch: [514, 528],
  ce_branch: [775, 472], fw_branch: [775, 532], policy_branch: [775, 628],
  internet: [1058, 408], hzalo: [1096, 208], hcall: [1096, 270], hsocial: [1096, 560],
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
  if (nodePositions[dst]) {
    packet.setAttribute('cx', nodePositions[dst][0]);
    packet.setAttribute('cy', nodePositions[dst][1]);
  }
  packet.classList.add('active');
  if (blocked && nodePositions[dst]) {
    const xmark = document.getElementById('xmark');
    const [x, y] = nodePositions[dst];
    xmark.querySelectorAll('line')[0].setAttribute('x1', x + 12);
    xmark.querySelectorAll('line')[0].setAttribute('y1', y + 12);
    xmark.querySelectorAll('line')[0].setAttribute('x2', x + 44);
    xmark.querySelectorAll('line')[0].setAttribute('y2', y + 44);
    xmark.querySelectorAll('line')[1].setAttribute('x1', x + 44);
    xmark.querySelectorAll('line')[1].setAttribute('y1', y + 12);
    xmark.querySelectorAll('line')[1].setAttribute('x2', x + 12);
    xmark.querySelectorAll('line')[1].setAttribute('y2', y + 44);
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
