from __future__ import annotations


LIVE_DASHBOARD_HTML = """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Giám sát SDN Call Center CCH</title>
  <style>
    :root {
      color: #172033; background: #eef2f5;
      font-family: Inter, "Segoe UI", system-ui, sans-serif;
      --green: #087f5b; --red: #c92a2a; --amber: #d97706;
      --blue: #2563eb; --ink: #172033; --line: #aebdcc;
    }
    * { box-sizing: border-box; }
    body { margin: 0; }
    button, input, select { font: inherit; }
    main { min-height: 100vh; padding: 16px; }
    header, section { background: #fff; border: 1px solid #d9e1e8; border-radius: 8px; }
    header { align-items: center; display: flex; gap: 18px; justify-content: space-between; margin-bottom: 12px; padding: 15px 18px; }
    h1 { font-size: 23px; line-height: 1.2; margin: 0 0 4px; }
    h2 { font-size: 16px; margin: 0; }
    h3 { font-size: 13px; margin: 0 0 5px; }
    p { color: #607084; line-height: 1.45; margin: 0; }
    button { align-items: center; background: #fff; border: 1px solid #c8d3df; border-radius: 7px; color: var(--ink); cursor: pointer; display: inline-flex; gap: 7px; justify-content: center; min-height: 38px; padding: 8px 11px; }
    button:hover { border-color: #778ba0; box-shadow: 0 4px 12px rgba(23,32,51,.09); }
    button:disabled { cursor: wait; opacity: .55; }
    .primary { background: var(--green); border-color: var(--green); color: #fff; }
    .danger { border-color: #efaaa4; color: #a51d1d; }
    .layout { display: grid; gap: 12px; grid-template-columns: minmax(700px, 1fr) 380px; }
    .layout > *, .panel { min-width: 0; }
    .panel { max-width: 100%; overflow: hidden; }
    .panel-head { align-items: center; background: #f8fafc; border-bottom: 1px solid #e1e7ed; display: flex; gap: 12px; justify-content: space-between; min-height: 47px; padding: 10px 13px; }
    .panel-head span { color: #68788a; font-size: 12px; }
    .content { padding: 12px; }
    .system-info { display: grid; gap: 10px; grid-template-columns: repeat(3, 1fr); margin-bottom: 12px; }
    .system-info div { border-left: 3px solid var(--blue); padding: 4px 10px; }
    .system-info div:nth-child(2) { border-color: var(--green); }
    .system-info div:nth-child(3) { border-color: var(--amber); }
    .system-info p { font-size: 12px; }
    .stats { display: grid; gap: 8px; grid-template-columns: repeat(5, minmax(0, 1fr)); margin-bottom: 12px; }
    .stat { border: 1px solid #dde5ec; border-radius: 7px; min-height: 71px; padding: 9px; }
    .stat strong { display: block; font-size: 20px; line-height: 1.2; }
    .stat span { color: #6a798b; font-size: 11px; }
    .topology { background: #f9fbfc; border: 1px solid #dce4eb; border-radius: 7px; max-width: 100%; overflow: auto; }
    svg { display: block; height: auto; min-width: 1050px; width: 100%; }
    .zone { fill: #fff; stroke: #d8e1e9; stroke-width: 1.5; }
    .zone-title { fill: #607084; font-size: 13px; font-weight: 700; letter-spacing: 0; }
    .net-link { fill: none; stroke: var(--line); stroke-linecap: round; stroke-linejoin: round; stroke-width: 3; transition: stroke .2s, stroke-width .2s; }
    .net-link.control { stroke: #8b5cf6; stroke-dasharray: 7 7; }
    .net-link.active { stroke: #10a36f; stroke-width: 7; }
    .net-link.blocked { stroke: #dc2626; stroke-dasharray: 12 8; stroke-width: 7; }
    .node rect, .node polygon, .node ellipse { fill: #fff; stroke: #8da0b4; stroke-width: 2; }
    .node text { fill: var(--ink); font-size: 12px; font-weight: 650; pointer-events: none; text-anchor: middle; }
    .node .sub { fill: #68788a; font-size: 10px; font-weight: 500; }
    .node.user rect { fill: #eef6ff; stroke: #4b86c5; }
    .node.switch rect { fill: #ecfdf5; stroke: #15966b; }
    .node.security polygon { fill: #fff7ed; stroke: #d97706; }
    .node.service rect { fill: #f5f3ff; stroke: #7c5cc4; }
    .node.blocked rect { fill: #fff1f2; stroke: #dc2626; }
    .node.controller rect { fill: #ede9fe; stroke: #7c3aed; }
    .packet { fill: #16a36f; filter: drop-shadow(0 0 5px rgba(16,163,111,.7)); opacity: 0; stroke: #fff; stroke-width: 3; }
    .packet.show { opacity: 1; }
    .deny-x { display: none; }
    .deny-x.show { display: block; }
    .deny-x line { stroke: #dc2626; stroke-linecap: round; stroke-width: 10; }
    .legend { align-items: center; color: #66768a; display: flex; flex-wrap: wrap; font-size: 11px; gap: 14px; padding: 8px 2px 0; }
    .legend i { display: inline-block; height: 4px; margin-right: 5px; vertical-align: middle; width: 24px; }
    .form { display: grid; gap: 10px; grid-template-columns: 1fr 1fr; }
    label { color: #58687a; display: grid; font-size: 12px; gap: 5px; }
    select, input { background: #fff; border: 1px solid #c9d4df; border-radius: 7px; min-height: 38px; padding: 7px 8px; width: 100%; }
    .wide { grid-column: 1 / -1; }
    .actions { display: grid; gap: 7px; grid-template-columns: 1fr 1fr; margin-top: 11px; }
    .result { background: #f7f9fb; border-left: 4px solid #718096; border-radius: 7px; margin-top: 11px; min-height: 76px; padding: 10px; }
    .result.ok { border-color: var(--green); }
    .result.bad { border-color: var(--red); }
    .result strong { display: block; font-size: 14px; margin-bottom: 4px; }
    .result p { font-size: 12px; }
    .quality { display: grid; gap: 7px; grid-template-columns: 1fr 1fr; margin-top: 11px; }
    .quality div { border: 1px solid #dfe6ed; border-radius: 7px; padding: 8px; }
    .quality strong { display: block; font-size: 17px; }
    .quality span { color: #68788a; font-size: 11px; }
    .pass { color: var(--green); }
    .fail { color: var(--red); }
    pre { background: #111827; border-radius: 7px; color: #dce6f2; font-size: 12px; line-height: 1.45; margin: 0; max-height: 300px; overflow: auto; padding: 12px; white-space: pre-wrap; }
    .table-wrap { max-height: 340px; overflow: auto; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border-bottom: 1px solid #e8edf2; font-size: 12px; padding: 8px; text-align: left; vertical-align: top; }
    th { background: #f7f9fb; color: #536477; position: sticky; top: 0; }
    .badge { border-radius: 999px; display: inline-block; font-size: 10px; font-weight: 700; padding: 3px 7px; }
    .allow { background: #dcfce7; color: #087f5b; }
    .drop { background: #fee2e2; color: #b42318; }
    .status-up { color: var(--green); font-weight: 700; }
    .status-down { color: var(--red); font-weight: 700; }
    @media (max-width: 1120px) { .layout { grid-template-columns: 1fr; } }
    @media (max-width: 700px) { main { padding: 8px; } header { align-items: flex-start; flex-direction: column; } .stats { grid-template-columns: 1fr 1fr; } .system-info, .form, .actions { grid-template-columns: 1fr; } .wide { grid-column: auto; } }
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Giám sát SDN Call Center CCH</h1>
      <p>Điều khiển OpenFlow và đo kiểm trực tiếp trên Mininet/Open vSwitch.</p>
    </div>
    <button class="primary" onclick="refreshAll()">↻ Làm mới dữ liệu</button>
  </header>

  <div class="system-info">
    <div><h3>Mạng người dùng</h3><p>Các dự án tại Trụ sở và Telesale/Backoffice tại Chi nhánh được tách theo VLAN.</p></div>
    <div><h3>Điều khiển SDN</h3><p>Controller áp chính sách allow/drop xuống OVS qua OpenFlow 1.3, mặc định từ chối.</p></div>
    <div><h3>Dịch vụ Call Center</h3><p>Cho phép Voice, Zalo, Call App; chặn mạng xã hội. KPI thoại được đo từ lưu lượng thật.</p></div>
  </div>

  <div class="stats">
    <div class="stat"><strong id="hostCount">0/9</strong><span>Host Mininet hoạt động</span></div>
    <div class="stat"><strong id="flowCount">0</strong><span>Luồng OpenFlow</span></div>
    <div class="stat"><strong id="rttValue">--</strong><span>RTT trung bình (ms)</span></div>
    <div class="stat"><strong id="jitterValue">--</strong><span>Jitter UDP (ms)</span></div>
    <div class="stat"><strong id="mosValue">--</strong><span>MOS ước lượng / 4.5</span></div>
  </div>

  <div class="layout">
    <div>
      <section class="panel">
        <div class="panel-head"><h2>Sơ đồ logic và luồng gói tin</h2><span id="liveStatus">Đang kiểm tra...</span></div>
        <div class="content">
          <div class="topology">
            <svg viewBox="0 0 1400 820" role="img" aria-label="Sơ đồ mạng SDN Call Center">
              <defs>
                <marker id="arrowGreen" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4"><path d="M0 0 L8 4 L0 8 Z" fill="#10a36f"/></marker>
                <marker id="arrowRed" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4"><path d="M0 0 L8 4 L0 8 Z" fill="#dc2626"/></marker>
              </defs>

              <rect class="zone" x="20" y="85" width="620" height="410" rx="7"/>
              <text class="zone-title" x="38" y="110">TRỤ SỞ CHÍNH (HQ)</text>
              <rect class="zone" x="20" y="520" width="620" height="270" rx="7"/>
              <text class="zone-title" x="38" y="545">CHI NHÁNH (BRANCH)</text>
              <rect class="zone" x="660" y="205" width="270" height="585" rx="7"/>
              <text class="zone-title" x="678" y="230">AN NINH & CHÍNH SÁCH</text>
              <rect class="zone" x="950" y="85" width="430" height="705" rx="7"/>
              <text class="zone-title" x="968" y="110">DỊCH VỤ / INTERNET</text>

              <path id="link-h20-access_hq_a" class="net-link" d="M180 155 L260 155"/>
              <path id="link-h30-access_hq_b" class="net-link" d="M180 235 L260 235"/>
              <path id="link-h40-access_hq_c" class="net-link" d="M180 315 L260 315"/>
              <path id="link-h90-voice_mgmt" class="net-link" d="M180 430 L260 430"/>
              <path id="link-access_hq_a-core_hq" class="net-link" d="M410 155 L490 245"/>
              <path id="link-access_hq_b-core_hq" class="net-link" d="M410 235 L490 265"/>
              <path id="link-access_hq_c-core_hq" class="net-link" d="M410 315 L490 285"/>
              <path id="link-voice_mgmt-core_hq" class="net-link" d="M410 430 L490 305"/>
              <path id="link-core_hq-fw_hq" class="net-link" d="M610 275 L685 335"/>
              <path id="link-fw_hq-policy_hq" class="net-link" d="M745 365 L745 430"/>
              <path id="link-policy_hq-internet" class="net-link" d="M805 460 L1005 460"/>

              <path id="link-h50-access_branch" class="net-link" d="M180 610 L280 650"/>
              <path id="link-h60-access_branch" class="net-link" d="M180 710 L280 670"/>
              <path id="link-access_branch-dist_branch" class="net-link" d="M430 660 L490 660"/>
              <path id="link-dist_branch-fw_branch" class="net-link" d="M610 660 L685 610"/>
              <path id="link-fw_branch-policy_branch" class="net-link" d="M745 640 L745 700"/>
              <path id="link-policy_branch-internet" class="net-link" d="M805 730 L1005 500"/>
              <path id="link-dist_branch-wan" class="net-link" d="M550 630 L550 500"/>
              <path id="link-wan-core_hq" class="net-link" d="M550 500 L550 310"/>

              <path id="link-internet-hzalo" class="net-link" d="M1125 470 L1185 240"/>
              <path id="link-internet-hcall" class="net-link" d="M1125 480 L1185 390"/>
              <path id="link-internet-hsocial" class="net-link" d="M1125 500 L1185 555"/>
              <path id="link-c0-core_hq" class="net-link control" d="M745 150 L590 240"/>
              <path id="link-c0-dist_branch" class="net-link control" d="M745 150 L590 625"/>

              <g id="h20" class="node user" transform="translate(60 130)"><rect width="120" height="50" rx="6"/><text x="60" y="20">Dự án A</text><text class="sub" x="60" y="36">h20 · VLAN 20</text></g>
              <g id="h30" class="node user" transform="translate(60 210)"><rect width="120" height="50" rx="6"/><text x="60" y="20">Dự án B</text><text class="sub" x="60" y="36">h30 · VLAN 30</text></g>
              <g id="h40" class="node user" transform="translate(60 290)"><rect width="120" height="50" rx="6"/><text x="60" y="20">Dự án C</text><text class="sub" x="60" y="36">h40 · VLAN 40</text></g>
              <g id="h90" class="node service" transform="translate(60 405)"><rect width="120" height="50" rx="6"/><text x="60" y="20">Voice Service</text><text class="sub" x="60" y="36">h90 · VLAN 90</text></g>
              <g id="access_hq_a" class="node switch" transform="translate(260 132)"><rect width="150" height="46" rx="5"/><text x="75" y="19">Access HQ-A</text><text class="sub" x="75" y="34">Open vSwitch</text></g>
              <g id="access_hq_b" class="node switch" transform="translate(260 212)"><rect width="150" height="46" rx="5"/><text x="75" y="19">Access HQ-B</text><text class="sub" x="75" y="34">Open vSwitch</text></g>
              <g id="access_hq_c" class="node switch" transform="translate(260 292)"><rect width="150" height="46" rx="5"/><text x="75" y="19">Access HQ-C</text><text class="sub" x="75" y="34">Open vSwitch</text></g>
              <g id="voice_mgmt" class="node switch" transform="translate(260 407)"><rect width="150" height="46" rx="5"/><text x="75" y="19">Voice Management</text><text class="sub" x="75" y="34">VLAN 90</text></g>
              <g id="core_hq" class="node switch" transform="translate(490 240)"><rect width="120" height="70" rx="6"/><text x="60" y="28">HQ Core SDN</text><text class="sub" x="60" y="47">OVS · OpenFlow 1.3</text></g>
              <g id="wan" class="node switch" transform="translate(500 470)"><rect width="100" height="45" rx="5"/><text x="50" y="19">WAN mô phỏng</text><text class="sub" x="50" y="34">Site Link</text></g>

              <g id="h50" class="node user" transform="translate(60 585)"><rect width="120" height="50" rx="6"/><text x="60" y="20">Telesale</text><text class="sub" x="60" y="36">h50 · VLAN 50</text></g>
              <g id="h60" class="node user" transform="translate(60 685)"><rect width="120" height="50" rx="6"/><text x="60" y="20">Backoffice</text><text class="sub" x="60" y="36">h60 · VLAN 60</text></g>
              <g id="access_branch" class="node switch" transform="translate(280 635)"><rect width="150" height="50" rx="5"/><text x="75" y="20">Branch Access</text><text class="sub" x="75" y="36">Open vSwitch</text></g>
              <g id="dist_branch" class="node switch" transform="translate(490 625)"><rect width="120" height="70" rx="6"/><text x="60" y="28">Branch Dist.</text><text class="sub" x="60" y="47">SDN Dataplane</text></g>

              <g id="c0" class="node controller" transform="translate(665 105)"><rect width="160" height="65" rx="6"/><text x="80" y="26">SDN Controller</text><text class="sub" x="80" y="44">127.0.0.1:6653</text></g>
              <g id="fw_hq" class="node security" transform="translate(685 305)"><polygon points="0,30 30,0 90,0 120,30 90,60 30,60"/><text x="60" y="27">Firewall HQ</text><text class="sub" x="60" y="43">Security</text></g>
              <g id="policy_hq" class="node security" transform="translate(685 430)"><polygon points="0,30 30,0 90,0 120,30 90,60 30,60"/><text x="60" y="27">Policy HQ</text><text class="sub" x="60" y="43">Allow / Drop</text></g>
              <g id="fw_branch" class="node security" transform="translate(685 580)"><polygon points="0,30 30,0 90,0 120,30 90,60 30,60"/><text x="60" y="27">Firewall Branch</text><text class="sub" x="60" y="43">Security</text></g>
              <g id="policy_branch" class="node security" transform="translate(685 700)"><polygon points="0,30 30,0 90,0 120,30 90,60 30,60"/><text x="60" y="27">Policy Branch</text><text class="sub" x="60" y="43">Allow / Drop</text></g>

              <g id="internet" class="node switch" transform="translate(1005 440)"><rect width="120" height="70" rx="6"/><text x="60" y="28">Internet Zone</text><text class="sub" x="60" y="47">Service Gateway</text></g>
              <g id="hzalo" class="node service" transform="translate(1185 210)"><rect width="140" height="60" rx="6"/><text x="70" y="25">Zalo Service</text><text class="sub" x="70" y="43">hzalo · Cho phép</text></g>
              <g id="hcall" class="node service" transform="translate(1185 360)"><rect width="140" height="60" rx="6"/><text x="70" y="25">Call App</text><text class="sub" x="70" y="43">hcall · Cho phép</text></g>
              <g id="hsocial" class="node blocked" transform="translate(1185 525)"><rect width="140" height="60" rx="6"/><text x="70" y="25">Mạng xã hội</text><text class="sub" x="70" y="43">hsocial · Bị chặn</text></g>

              <circle id="packet" class="packet" cx="120" cy="155" r="10"/>
              <g id="denyX" class="deny-x"><line x1="-15" y1="-15" x2="15" y2="15"/><line x1="15" y1="-15" x2="-15" y2="15"/></g>
            </svg>
          </div>
          <div class="legend">
            <span><i style="background:#aebdcc"></i>Liên kết mạng</span>
            <span><i style="background:#10a36f"></i>Luồng được phép</span>
            <span><i style="background:#dc2626"></i>Luồng bị chặn</span>
            <span><i style="background:#8b5cf6"></i>Kênh điều khiển OpenFlow</span>
          </div>
        </div>
      </section>

      <section class="panel" style="margin-top:12px">
        <div class="panel-head"><h2>Bảng luồng OpenFlow dễ đọc</h2><button onclick="loadFlows()">↻ Đọc lại flow</button></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Diễn giải</th><th>Nguồn → Đích</th><th>Quyết định</th><th>Ưu tiên</th><th>Bộ đếm</th></tr></thead>
            <tbody id="flowRows"><tr><td colspan="5">Đang tải dữ liệu...</td></tr></tbody>
          </table>
        </div>
      </section>
    </div>

    <aside>
      <section class="panel">
        <div class="panel-head"><h2>Đo kiểm và điều khiển</h2><span>Dữ liệu thật từ Mininet</span></div>
        <div class="content">
          <div class="form">
            <label>Nguồn<select id="source"></select></label>
            <label>Đích<select id="destination"></select></label>
            <label class="wide">Thời gian đo iperf (giây)<input id="seconds" type="number" min="1" max="60" value="5"></label>
          </div>
          <div class="actions">
            <button class="primary" onclick="runPing()">→ Ping thực tế</button>
            <button class="primary" onclick="runCallQuality()">☎ Chất lượng cuộc gọi</button>
            <button onclick="runIperf('tcp')">⇄ Băng thông TCP</button>
            <button onclick="runIperf('udp')">⇄ Băng thông UDP</button>
            <button class="danger" onclick="blockPair()">× Chặn bằng OpenFlow</button>
            <button onclick="unblockPair()">✓ Gỡ chặn</button>
          </div>
          <div id="result" class="result"><strong>Sẵn sàng đo kiểm</strong><p>Chọn nguồn, đích và một phép đo.</p></div>
          <div class="quality">
            <div><strong id="qualityRtt">--</strong><span>RTT ≤ 150 ms</span></div>
            <div><strong id="qualityJitter">--</strong><span>Jitter ≤ 30 ms</span></div>
            <div><strong id="qualityLoss">--</strong><span>Mất gói ≤ 1%</span></div>
            <div><strong id="qualityMos">--</strong><span>MOS ≥ 4.0</span></div>
            <div><strong id="qualityThroughput">--</strong><span>UDP ≥ 0.1 Mbps</span></div>
            <div><strong id="qualityRFactor">--</strong><span>R-factor / 100</span></div>
          </div>
        </div>
      </section>

      <section class="panel" style="margin-top:12px">
        <div class="panel-head"><h2>Kết quả lệnh thực tế</h2><span id="lastAction">Sẵn sàng</span></div>
        <div class="content"><pre id="output">Kết quả từ namespace Mininet sẽ hiển thị tại đây.</pre></div>
      </section>
    </aside>
  </div>
</main>

<script>
const api = async (path, options = {}) => {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`Máy chủ trả về HTTP ${response.status}`);
  return response.json();
};
const post = (path, body) => api(path, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});
const pair = () => ({
  source: document.getElementById('source').value,
  destination: document.getElementById('destination').value,
});
const positions = {
  h20:[120,155], h30:[120,235], h40:[120,315], h90:[120,430],
  access_hq_a:[335,155], access_hq_b:[335,235], access_hq_c:[335,315], voice_mgmt:[335,430],
  core_hq:[550,275], wan:[550,492], h50:[120,610], h60:[120,710],
  access_branch:[355,660], dist_branch:[550,660], c0:[745,137],
  fw_hq:[745,335], policy_hq:[745,460], fw_branch:[745,610], policy_branch:[745,730],
  internet:[1065,475], hzalo:[1255,240], hcall:[1255,390], hsocial:[1255,555],
};
let animationToken = 0;

function linkElement(a, b) {
  return document.getElementById(`link-${a}-${b}`) || document.getElementById(`link-${b}-${a}`);
}
function clearPath() {
  animationToken += 1;
  document.querySelectorAll('.net-link').forEach((line) => line.classList.remove('active', 'blocked'));
  document.getElementById('packet').classList.remove('show');
  document.getElementById('denyX').classList.remove('show');
}
function movePacket(from, to, duration, token) {
  return new Promise((resolve) => {
    const packet = document.getElementById('packet');
    const started = performance.now();
    const frame = (now) => {
      if (token !== animationToken) return resolve();
      const progress = Math.min(1, (now - started) / duration);
      const eased = progress < .5 ? 2 * progress * progress : 1 - Math.pow(-2 * progress + 2, 2) / 2;
      packet.setAttribute('cx', from[0] + ((to[0] - from[0]) * eased));
      packet.setAttribute('cy', from[1] + ((to[1] - from[1]) * eased));
      if (progress < 1) requestAnimationFrame(frame); else resolve();
    };
    requestAnimationFrame(frame);
  });
}
async function animateDecision(payload) {
  clearPath();
  const decision = payload.decision || {};
  const fullPath = (decision.path || []).filter((id) => positions[id]);
  if (fullPath.length < 2) return;
  const denied = decision.action === 'deny' || (!payload.ok && !payload.measurement_completed);
  let path = fullPath;
  if (denied && decision.blocked_at && path.includes(decision.blocked_at)) {
    path = path.slice(0, path.indexOf(decision.blocked_at) + 1);
  }
  const token = animationToken;
  const packet = document.getElementById('packet');
  packet.setAttribute('cx', positions[path[0]][0]);
  packet.setAttribute('cy', positions[path[0]][1]);
  packet.classList.add('show');
  for (let i = 0; i < path.length - 1; i += 1) {
    if (token !== animationToken) return;
    const link = linkElement(path[i], path[i + 1]);
    if (link) link.classList.add(denied ? 'blocked' : 'active');
    await movePacket(positions[path[i]], positions[path[i + 1]], 430, token);
  }
  if (denied) {
    const end = positions[path[path.length - 1]];
    const mark = document.getElementById('denyX');
    mark.setAttribute('transform', `translate(${end[0]} ${end[1]})`);
    mark.classList.add('show');
    packet.classList.remove('show');
  }
}
function setBusy(busy) {
  document.querySelectorAll('button').forEach((button) => { button.disabled = busy; });
}
function show(title, payload) {
  document.getElementById('lastAction').textContent = title;
  document.getElementById('output').textContent =
    `${payload.message || title}\\n\\n${payload.raw || payload.result?.raw || JSON.stringify(payload, null, 2)}`;
  const result = document.getElementById('result');
  result.className = `result ${payload.ok ? 'ok' : 'bad'}`;
  result.innerHTML = `<strong>${payload.message || title}</strong><p>${payload.decision?.reason || 'Kết quả được lấy trực tiếp từ Mininet/Open vSwitch.'}</p>`;
}
function updateQuality(data = {}) {
  const fields = [
    ['qualityRtt', data.rtt_avg_ms, ' ms', data.checks?.latency],
    ['qualityJitter', data.jitter_ms, ' ms', data.checks?.jitter],
    ['qualityLoss', data.packet_loss_percent, '%', data.checks?.packet_loss],
    ['qualityMos', data.mos, ' / 4.5', data.checks?.mos],
    ['qualityThroughput', data.throughput_mbps, ' Mbps', data.checks?.throughput],
    ['qualityRFactor', data.r_factor, ' / 100', data.r_factor === undefined ? undefined : data.r_factor >= 80],
  ];
  fields.forEach(([id, value, suffix, passed]) => {
    const el = document.getElementById(id);
    el.textContent = value === undefined || value === null ? '--' : `${value}${suffix}`;
    el.className = passed === undefined ? '' : (passed ? 'pass' : 'fail');
  });
  if (data.rtt_avg_ms !== undefined) document.getElementById('rttValue').textContent = data.rtt_avg_ms;
  if (data.jitter_ms !== undefined) document.getElementById('jitterValue').textContent = data.jitter_ms;
  if (data.mos !== undefined) document.getElementById('mosValue').textContent = data.mos;
}
async function execute(title, request) {
  setBusy(true);
  show(`${title} đang chạy...`, { ok: true, raw: 'Đang thực thi trong namespace Mininet...' });
  try {
    const payload = await request();
    await animateDecision(payload);
    show(title, payload);
    if (payload.result) updateQuality(payload.result);
    await loadFlows();
  } catch (error) {
    show('Lỗi dashboard', { ok: false, raw: error.message });
  } finally {
    setBusy(false);
  }
}
async function loadTopology() {
  const topology = await api('/api/topology');
  const hosts = topology.nodes.filter((node) => node.id.startsWith('h'));
  for (const id of ['source', 'destination']) {
    document.getElementById(id).innerHTML = hosts
      .map((host) => `<option value="${host.id}">${host.label} (${host.ip})</option>`).join('');
  }
  document.getElementById('source').value = 'h20';
  document.getElementById('destination').value = 'h90';
}
async function loadStatus() {
  const status = await api('/api/live/status');
  const found = Object.values(status.hosts || {}).filter(Boolean).length;
  document.getElementById('hostCount').textContent = `${found}/9`;
  document.getElementById('liveStatus').innerHTML = status.ovs_bridge
    ? '<span class="status-up">● OVS s1 đang hoạt động</span>'
    : '<span class="status-down">● OVS s1 chưa hoạt động</span>';
}
async function loadFlows() {
  const payload = await api('/api/flows');
  const flows = payload.flows || [];
  document.getElementById('flowRows').innerHTML = flows.length ? flows.map((flow) => `
    <tr><td>${flow.explanation}</td><td>${flow.match}</td>
    <td><span class="badge ${flow.action === 'ALLOW' ? 'allow' : 'drop'}">${flow.action === 'ALLOW' ? 'CHO PHÉP' : 'CHẶN'}</span></td>
    <td>${flow.priority}</td><td>${flow.packets} gói<br>${flow.bytes} byte</td></tr>`).join('')
    : '<tr><td colspan="5">Chưa đọc được flow. Hãy kiểm tra OVS s1 và quyền chạy dashboard.</td></tr>';
  document.getElementById('flowCount').textContent = flows.length;
}
function runPing() { return execute('Kết quả Ping', () => post('/api/test/ping', pair())); }
function runIperf(protocol) {
  const body = { ...pair(), protocol, seconds: Number(document.getElementById('seconds').value || 5) };
  return execute(`Đo băng thông ${protocol.toUpperCase()}`, () => post('/api/test/iperf', body));
}
function runCallQuality() {
  const body = { ...pair(), protocol: 'udp', seconds: Number(document.getElementById('seconds').value || 5) };
  return execute('Đánh giá chất lượng cuộc gọi', () => post('/api/test/call-quality', body));
}
async function blockPair() {
  const payload = await post('/api/live/block', pair()); show('Chặn OpenFlow', payload); await loadFlows();
}
async function unblockPair() {
  const payload = await post('/api/live/unblock', pair()); show('Gỡ chặn OpenFlow', payload); await loadFlows();
}
async function refreshAll() { clearPath(); await loadTopology(); await loadStatus(); await loadFlows(); }
refreshAll().catch((error) => show('Lỗi dashboard', { ok: false, raw: error.message }));
</script>
</body>
</html>
"""
