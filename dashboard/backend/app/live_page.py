from __future__ import annotations


LIVE_DASHBOARD_HTML = """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hybrid MPLS L3VPN + SDN Edge Policy Demo</title>
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
    .sdn-explainer { border-left: 4px solid #7c3aed; margin-bottom: 12px; padding: 11px 14px; }
    .sdn-explainer p { font-size: 12px; }
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
    .policy-map { pointer-events: none; stroke-linecap: round; stroke-width: 5; }
    .policy-map.allow { stroke: #10a36f; stroke-opacity: .58; }
    .policy-map.deny { stroke: #dc2626; stroke-dasharray: 10 8; stroke-opacity: .72; }
    .node rect, .node polygon, .node ellipse { fill: #fff; stroke: #8da0b4; stroke-width: 2; }
    .node.selectable { cursor: pointer; }
    .node.selected rect, .node.selected polygon, .node.selected ellipse { stroke: #111827; stroke-width: 4; }
    .node text { fill: var(--ink); font-size: 12px; font-weight: 650; pointer-events: none; text-anchor: middle; }
    .node .sub { fill: #68788a; font-size: 10px; font-weight: 500; }
    .node.user rect { fill: #eef6ff; stroke: #4b86c5; }
    .node.switch rect { fill: #ecfdf5; stroke: #15966b; }
    .node.security polygon { fill: #fff7ed; stroke: #d97706; }
    .node.service rect { fill: #f5f3ff; stroke: #7c5cc4; }
    .node.blocked rect { fill: #fff1f2; stroke: #dc2626; }
    .node.controller rect { fill: #ede9fe; stroke: #7c3aed; }
    .node.router rect { fill: #eff6ff; stroke: #3974b8; }
    .node.cloud ellipse { fill: #f3f0ff; stroke: #7765a8; }
    .net-link.mpls { stroke: #7765a8; stroke-width: 4; }
    .policy-note { fill: #fbfcfe; stroke: #c8d2dd; stroke-dasharray: 5 4; }
    .policy-text { fill: #526276; font-size: 10px; }
    .packet { fill: #16a36f; filter: drop-shadow(0 0 5px rgba(16,163,111,.7)); opacity: 0; stroke: #fff; stroke-width: 3; }
    .packet.show { opacity: 1; }
    .deny-x { display: none; }
    .deny-x.show { display: block; }
    .deny-x line { stroke: #dc2626; stroke-linecap: round; stroke-width: 10; }
    .legend { align-items: center; color: #66768a; display: flex; flex-wrap: wrap; font-size: 11px; gap: 14px; padding: 8px 2px 0; }
    .legend i { display: inline-block; height: 4px; margin-right: 5px; vertical-align: middle; width: 24px; }
    .cluster-policy { border-top: 1px solid #e1e7ed; display: grid; gap: 5px; margin-top: 8px; padding: 10px 2px 0; }
    .cluster-policy strong { font-size: 13px; }
    .cluster-policy p, .cluster-policy div { color: #607084; font-size: 12px; line-height: 1.4; margin: 0; }
    .cluster-policy span { font-weight: 750; }
    .cluster-policy .ok { color: var(--green); }
    .cluster-policy .bad { color: var(--red); }
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
      <h1>Giám sát Hybrid MPLS L3VPN + SDN Call Center CCH</h1>
      <p>SDN Controller điều khiển Open vSwitch tại edge/access; MPLS L3VPN là WAN transport giữa hai site.</p>
    </div>
    <button class="primary" onclick="refreshAll()">↻ Làm mới dữ liệu</button>
  </header>

  <div class="system-info">
    <div><h3>Mạng người dùng</h3><p>Các Project/VLAN tại HQ và Branch được tách riêng để dễ áp chính sách và đo kiểm.</p></div>
    <div><h3>Điều khiển SDN</h3><p>Controller cài flow allow/drop/steering xuống Open vSwitch qua OpenFlow 1.3.</p></div>
    <div><h3>WAN/MPLS và Internet</h3><p>Traffic liên site qua MPLS L3VPN; traffic Internet đi qua Firewall của từng site.</p></div>
  </div>
  <section class="sdn-explainer">
    <h3>SDN hoạt động như thế nào?</h3>
    <p>SDN Controller là bộ não điều khiển mạng. Khi Open vSwitch chưa có rule cho một luồng mới, switch gửi Packet-In lên controller. Controller kiểm tra policy, tính đường đi và cài Flow-Mod; các gói tiếp theo được switch xử lý trực tiếp. Controller chỉ điều khiển OVS qua OpenFlow 1.3, không điều khiển MPLS L3VPN Cloud.</p>
  </section>

  <div class="stats">
    <div class="stat"><strong id="hostCount">0/109</strong><span>Endpoint Mininet hoạt động</span></div>
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
            <svg viewBox="0 0 1600 900" role="img" aria-label="Sơ đồ Hybrid MPLS L3VPN và SDN Edge Policy">
              <defs>
                <marker id="arrowGreen" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4"><path d="M0 0 L8 4 L0 8 Z" fill="#10a36f"/></marker>
                <marker id="arrowRed" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4"><path d="M0 0 L8 4 L0 8 Z" fill="#dc2626"/></marker>
              </defs>

              <rect class="zone" x="20" y="90" width="720" height="420" rx="7"/>
              <text class="zone-title" x="38" y="116">TRỤ SỞ CHÍNH · FIREWALL HQ TẠI BIÊN SITE</text>
              <rect class="zone" x="20" y="535" width="720" height="340" rx="7"/>
              <text class="zone-title" x="38" y="561">CHI NHÁNH · FIREWALL BRANCH TẠI BIÊN SITE</text>
              <rect class="zone" x="760" y="210" width="340" height="665" rx="7"/>
              <text class="zone-title" x="778" y="236">WAN / MPLS L3VPN</text>
              <rect class="zone" x="1120" y="90" width="460" height="785" rx="7"/>
              <text class="zone-title" x="1138" y="116">DỊCH VỤ / INTERNET</text>

              <path id="link-project_a-access_hq_a" class="net-link" d="M165 160 L225 160"/>
              <path id="link-project_b-access_hq_b" class="net-link" d="M165 240 L225 240"/>
              <path id="link-project_c-access_hq_c" class="net-link" d="M165 320 L225 320"/>
              <path id="link-it_support-access_hq_it" class="net-link" d="M165 390 L225 390"/>
              <path id="link-h90-voice_mgmt" class="net-link" d="M165 465 L225 465"/>
              <path id="link-access_hq_a-core_hq" class="net-link" d="M365 160 L430 250"/>
              <path id="link-access_hq_b-core_hq" class="net-link" d="M365 240 L430 275"/>
              <path id="link-access_hq_c-core_hq" class="net-link" d="M365 320 L430 300"/>
              <path id="link-access_hq_it-core_hq" class="net-link" d="M365 390 L430 315"/>
              <path id="link-voice_mgmt-core_hq" class="net-link" d="M365 465 L430 325"/>

              <path id="link-telesale-access_branch" class="net-link" d="M165 635 L230 675"/>
              <path id="link-backoffice-access_branch" class="net-link" d="M165 760 L230 700"/>
              <path id="link-access_branch-dist_branch" class="net-link" d="M370 687 L430 687"/>

              <path id="link-core_hq-ce_hq" class="net-link mpls" d="M550 300 L820 285"/>
              <path id="link-ce_hq-mpls_cloud" class="net-link mpls" d="M960 285 L950 355"/>
              <path id="link-mpls_cloud-ce_branch" class="net-link mpls" d="M950 465 L960 655"/>
              <path id="link-ce_branch-dist_branch" class="net-link mpls" d="M820 655 L550 687"/>

              <path id="link-core_hq-fw_hq" class="net-link" d="M550 307 H585 V440 H620"/>
              <path id="link-fw_hq-internet" class="net-link" d="M740 440 H1040 V600 H1200"/>
              <path id="link-dist_branch-fw_branch" class="net-link" d="M550 707 H585 V760 H620"/>
              <path id="link-fw_branch-internet" class="net-link" d="M740 760 H1040 V600 H1200"/>

              <path id="link-internet-hzalo" class="net-link" d="M1320 600 L1400 210"/>
              <path id="link-internet-hcall" class="net-link" d="M1320 600 L1400 350"/>
              <path id="link-internet-hsocial" class="net-link" d="M1320 600 L1400 570"/>
              <path id="link-internet-hinternet" class="net-link" d="M1320 600 L1400 790"/>

              <path id="link-c0-core_hq" class="net-link control" d="M930 145 L510 250"/>
              <path id="link-c0-dist_branch" class="net-link control" d="M930 145 L510 650"/>
              <path id="link-c0-access_hq_a" class="net-link control" d="M900 140 L330 145"/>
              <path id="link-c0-access_hq_b" class="net-link control" d="M900 145 L340 225"/>
              <path id="link-c0-access_hq_c" class="net-link control" d="M910 155 L350 305"/>
              <path id="link-c0-access_hq_it" class="net-link control" d="M920 162 L350 390"/>
              <path id="link-c0-access_branch" class="net-link control" d="M950 170 L335 655"/>

              <g id="project_a" class="node user" transform="translate(45 135)"><rect width="120" height="50" rx="5"/><text x="60" y="19">Dự án A</text><text class="sub" x="60" y="35">20 user · VLAN 20</text></g>
              <g id="project_b" class="node user" transform="translate(45 215)"><rect width="120" height="50" rx="5"/><text x="60" y="19">Dự án B</text><text class="sub" x="60" y="35">20 user · VLAN 30</text></g>
              <g id="project_c" class="node user" transform="translate(45 295)"><rect width="120" height="50" rx="5"/><text x="60" y="19">Dự án C</text><text class="sub" x="60" y="35">20 user · VLAN 40</text></g>
              <g id="it_support" class="node user" transform="translate(45 365)"><rect width="120" height="50" rx="5"/><text x="60" y="19">Phòng IT</text><text class="sub" x="60" y="35">4 user · VLAN 70</text></g>
              <g id="h90" class="node service" transform="translate(45 440)"><rect width="120" height="50" rx="5"/><text x="60" y="19">Voice Cluster</text><text class="sub" x="60" y="35">PBX/SBC/SIP-RTP</text></g>
              <g id="access_hq_a" class="node switch" transform="translate(225 137)"><rect width="140" height="46" rx="5"/><text x="70" y="19">Access HQ-A</text><text class="sub" x="70" y="34">Open vSwitch</text></g>
              <g id="access_hq_b" class="node switch" transform="translate(225 217)"><rect width="140" height="46" rx="5"/><text x="70" y="19">Access HQ-B</text><text class="sub" x="70" y="34">Open vSwitch</text></g>
              <g id="access_hq_c" class="node switch" transform="translate(225 297)"><rect width="140" height="46" rx="5"/><text x="70" y="19">Access HQ-C</text><text class="sub" x="70" y="34">Open vSwitch</text></g>
              <g id="access_hq_it" class="node switch" transform="translate(225 367)"><rect width="140" height="46" rx="5"/><text x="70" y="19">Access HQ-IT</text><text class="sub" x="70" y="34">Open vSwitch</text></g>
              <g id="voice_mgmt" class="node switch" transform="translate(225 442)"><rect width="140" height="46" rx="5"/><text x="70" y="19">Voice Access</text><text class="sub" x="70" y="34">VLAN 90</text></g>
              <g id="core_hq" class="node switch" transform="translate(430 250)"><rect width="120" height="75" rx="6"/><text x="60" y="29">HQ Core SDN</text><text class="sub" x="60" y="49">OVS · OpenFlow 1.3</text></g>

              <g id="telesale" class="node user" transform="translate(45 610)"><rect width="120" height="50" rx="5"/><text x="60" y="19">Telesale</text><text class="sub" x="60" y="35">20 user · VLAN 50</text></g>
              <g id="backoffice" class="node user" transform="translate(45 735)"><rect width="120" height="50" rx="5"/><text x="60" y="19">BackOffice</text><text class="sub" x="60" y="35">20 user · VLAN 60</text></g>
              <g id="access_branch" class="node switch" transform="translate(230 662)"><rect width="140" height="50" rx="5"/><text x="70" y="20">Branch Access</text><text class="sub" x="70" y="36">Open vSwitch</text></g>
              <g id="dist_branch" class="node switch" transform="translate(430 650)"><rect width="120" height="75" rx="6"/><text x="60" y="29">Branch Distribution</text><text class="sub" x="60" y="49">OVS · OpenFlow 1.3</text></g>

              <g id="c0" class="node controller" transform="translate(850 105)"><rect width="160" height="65" rx="6"/><text x="80" y="26">SDN Controller</text><text class="sub" x="80" y="44">127.0.0.1:6653</text></g>
              <g id="ce_hq" class="node router" transform="translate(820 255)"><rect width="140" height="60" rx="6"/><text x="70" y="25">CE Router HQ</text><text class="sub" x="70" y="43">Customer Edge</text></g>
              <g id="mpls_cloud" class="node cloud"><ellipse cx="950" cy="410" rx="105" ry="55"/><text x="950" y="401">MPLS L3VPN Cloud</text><text class="sub" x="950" y="421">ISP quản lý · WAN transport</text></g>
              <g id="ce_branch" class="node router" transform="translate(820 625)"><rect width="140" height="60" rx="6"/><text x="70" y="25">CE Router Branch</text><text class="sub" x="70" y="43">Customer Edge</text></g>
              <text class="policy-text" x="780" y="760">Liên site: Core/Dist → CE → MPLS → CE. Không đi qua Firewall.</text>
              <text class="policy-text" x="780" y="785">Internet/service: Core/Dist → Firewall site → Internet Zone.</text>
              <text class="policy-text" x="785" y="830">Controller không điều khiển CE Router hoặc MPLS Cloud.</text>

              <g id="fw_hq" class="node security" transform="translate(620 410)"><polygon points="0,30 30,0 90,0 120,30 90,60 30,60"/><text x="60" y="27">Firewall HQ</text><text class="sub" x="60" y="43">HQ Internet Edge</text></g>
              <g id="fw_branch" class="node security" transform="translate(620 730)"><polygon points="0,30 30,0 90,0 120,30 90,60 30,60"/><text x="60" y="27">Firewall Branch</text><text class="sub" x="60" y="43">Branch Internet Edge</text></g>
              <g id="internet" class="node switch" transform="translate(1200 565)"><rect width="120" height="70" rx="6"/><text x="60" y="28">Internet Zone</text><text class="sub" x="60" y="47">Service Gateway</text></g>
              <g id="hzalo" class="node service" transform="translate(1400 180)"><rect width="140" height="60" rx="6"/><text x="70" y="25">Zalo Service</text><text class="sub" x="70" y="43">hzalo · Cho phép</text></g>
              <g id="hcall" class="node service" transform="translate(1400 320)"><rect width="140" height="60" rx="6"/><text x="70" y="25">Call App / CRM</text><text class="sub" x="70" y="43">hcall · Cho phép</text></g>
              <g id="hsocial" class="node blocked" transform="translate(1400 540)"><rect width="140" height="60" rx="6"/><text x="70" y="25">Mạng xã hội</text><text class="sub" x="70" y="43">hsocial · Bị chặn</text></g>
              <g id="hinternet" class="node service" transform="translate(1400 760)"><rect width="140" height="60" rx="6"/><text x="70" y="25">Internet chung</text><text class="sub" x="70" y="43">hinternet · Kiểm thử</text></g>

              <circle id="packet" class="packet" cx="105" cy="160" r="10"/>
              <g id="denyX" class="deny-x"><line x1="-15" y1="-15" x2="15" y2="15"/><line x1="15" y1="-15" x2="-15" y2="15"/></g>
            </svg>
          </div>
          <div class="legend">
            <span><i style="background:#aebdcc"></i>Liên kết mạng</span>
            <span><i style="background:#10a36f"></i>Luồng được phép</span>
            <span><i style="background:#dc2626"></i>Luồng bị chặn</span>
            <span><i style="background:#8b5cf6"></i>Kênh điều khiển OpenFlow</span>
            <span><i style="background:#7765a8"></i>MPLS L3VPN / WAN transport</span>
            <span><i style="background:#d97706"></i>Firewall Internet Edge</span>
          </div>
          <div id="clusterPolicy" class="cluster-policy">
            <strong>Bấm vào từng cụm trên sơ đồ</strong>
            <p>Dashboard sẽ tô xanh các cụm được ping và tô đỏ các cụm bị chặn theo policy.</p>
          </div>
        </div>
      </section>

      <section class="panel" style="margin-top:12px">
        <div class="panel-head"><h2>Bảng luồng OpenFlow dễ đọc</h2><button onclick="loadFlows()">↻ Đọc lại flow</button></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Switch</th><th>Nguồn</th><th>Đích</th><th>Quyết định</th><th>Ưu tiên</th><th>Match</th><th>Action</th><th>Packet</th><th>Byte</th><th>Lý do</th></tr></thead>
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
          <div class="result">
            <strong>Test chi tiết theo cụm</strong>
            <p>Chạy Voice Cluster, Call App, Internet và các case segmentation cho từng nhóm.</p>
            <div class="form" style="margin-top:8px">
              <label>Cụm<select id="cluster">
                <option value="project_a">Dự án A</option>
                <option value="project_b">Dự án B</option>
                <option value="project_c">Dự án C</option>
                <option value="telesale">Telesale</option>
                <option value="backoffice">BackOffice</option>
                <option value="it_support">IT Support</option>
              </select></label>
              <label>Giây<input id="clusterSeconds" type="number" min="1" max="20" value="3"></label>
            </div>
            <button class="primary" style="margin-top:8px;width:100%" onclick="runClusterDetail()">Test chi tiết</button>
            <div id="clusterOutput" style="margin-top:8px"></div>
          </div>
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
  project_a:[105,160], project_b:[105,240], project_c:[105,320], it_support:[105,390], h90:[105,465],
  access_hq_a:[295,160], access_hq_b:[295,240], access_hq_c:[295,320], access_hq_it:[295,390], voice_mgmt:[295,465],
  core_hq:[490,287], fw_hq:[680,440], fw_branch:[680,760],
  ce_hq:[890,285], mpls_cloud:[950,410], ce_branch:[890,655],
  telesale:[105,635], backoffice:[105,760], access_branch:[300,687], dist_branch:[490,687],
  internet:[1260,600],
  hzalo:[1470,210], hcall:[1470,350], hsocial:[1470,570], hinternet:[1470,790],
  c0:[930,137],
};
const nodeNames = {
  project_a:'Dự án A', project_b:'Dự án B', project_c:'Dự án C', it_support:'Phòng IT',
  telesale:'Telesale', backoffice:'BackOffice', h90:'Voice Cluster', hzalo:'Zalo',
  hcall:'Call App', hsocial:'Mạng xã hội', hinternet:'Internet ngoài'
};
const pingPolicies = {
  project_a:{ title:'Dự án A / VLAN 20', allow:['h90','hzalo','hcall','hinternet'], deny:['project_b','project_c','telesale','backoffice','hsocial'], note:'Softphone chỉ đi tới PBX/SBC/SIP-RTP và Call App cần thiết, không mở ngang sang dự án khác.' },
  project_b:{ title:'Dự án B / VLAN 30', allow:['h90','hzalo','hcall','hinternet'], deny:['project_a','project_c','telesale','backoffice','hsocial'], note:'Cách ly Project A/C; voice đi về PBX/SIP-RTP service.' },
  project_c:{ title:'Dự án C / VLAN 40', allow:['h90','hzalo','hcall','hinternet'], deny:['project_a','project_b','telesale','backoffice','hsocial'], note:'Không cho agent ping ngang nhau giữa dự án.' },
  telesale:{ title:'Telesale / VLAN 50', allow:['h90','hzalo','hcall','hinternet'], deny:['project_a','project_b','project_c','backoffice','hsocial'], note:'Không mở full access qua MPLS sang các project HQ; chỉ IT Support có quyền hỗ trợ user.' },
  backoffice:{ title:'BackOffice / VLAN 60', allow:['h90','hzalo','hcall','hinternet'], deny:['telesale','project_a','project_b','project_c','hsocial'], note:'Không có full access sang HQ hoặc Telesale.' },
  it_support:{ title:'IT Support / VLAN 70', allow:['project_a','project_b','project_c','telesale','backoffice','h90','hzalo','hcall','hsocial','hinternet'], deny:[], note:'IT được full access để hỗ trợ/remote, Internet ngoài vẫn không được chủ động ping vào IT.' },
  h90:{ title:'Voice Cluster cho Cfono/Gphone', allow:['project_a','project_b','project_c','telesale','backoffice','it_support'], deny:['hzalo','hcall','hsocial','hinternet'], note:'PBX/SBC/SIP-RTP mô phỏng, không phải mở peer-to-peer giữa agent.' },
  hzalo:{ title:'Zalo Simulator', allow:[], deny:['project_a','project_b','project_c','telesale','backoffice','it_support'], note:'Service ngoài chỉ phản hồi phiên do user khởi tạo.' },
  hcall:{ title:'Call App / CRM', allow:[], deny:['project_a','project_b','project_c','telesale','backoffice','it_support'], note:'Ứng dụng ngoài không được chủ động mở kết nối vào máy agent.' },
  hsocial:{ title:'Mạng xã hội', allow:[], deny:['project_a','project_b','project_c','telesale','backoffice','it_support'], note:'User thường bị chặn Social; Social không được ping vào trong.' },
  hinternet:{ title:'Internet bên ngoài', allow:[], deny:['project_a','project_b','project_c','telesale','backoffice','it_support'], note:'Mặc định deny inbound từ Internet vào hệ thống nội bộ.' },
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
function clearPolicyMap() {
  document.querySelectorAll('.policy-map').forEach((line) => line.remove());
  document.querySelectorAll('.node.selected').forEach((node) => node.classList.remove('selected'));
}
function addPolicyLine(svg, sourceId, targetId, className) {
  if (!positions[sourceId] || !positions[targetId]) return;
  const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  line.setAttribute('x1', positions[sourceId][0]);
  line.setAttribute('y1', positions[sourceId][1]);
  line.setAttribute('x2', positions[targetId][0]);
  line.setAttribute('y2', positions[targetId][1]);
  line.setAttribute('class', `policy-map ${className}`);
  svg.insertBefore(line, svg.querySelector('.node') || document.getElementById('packet'));
}
function selectPolicyNode(nodeId) {
  const policy = pingPolicies[nodeId];
  if (!policy) return;
  clearPolicyMap();
  const svg = document.querySelector('.topology svg');
  document.getElementById(nodeId)?.classList.add('selected');
  policy.allow.forEach((target) => addPolicyLine(svg, nodeId, target, 'allow'));
  policy.deny.forEach((target) => addPolicyLine(svg, nodeId, target, 'deny'));
  document.getElementById('clusterPolicy').innerHTML = `
    <strong>${policy.title}</strong>
    <p>${policy.note}</p>
    <div><span class="ok">Được ping:</span> ${policy.allow.length ? policy.allow.map((id) => nodeNames[id]).join(', ') : 'Không chủ động ping vào nội bộ'}</div>
    <div><span class="bad">Không được ping:</span> ${policy.deny.length ? policy.deny.map((id) => nodeNames[id]).join(', ') : 'Không có mục chặn trong demo'}</div>`;
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
  const hosts = topology.hosts || [];
  for (const id of ['source', 'destination']) {
    document.getElementById(id).innerHTML = hosts
      .map((host) => `<option value="${host.name}">${host.label} (${host.name} - ${host.ip})</option>`).join('');
  }
  document.getElementById('source').value = 'h20_01';
  document.getElementById('destination').value = 'h90';
  document.getElementById('hostCount').dataset.total = hosts.length;
}
async function loadStatus() {
  const status = await api('/api/live/status');
  const found = Object.values(status.hosts || {}).filter(Boolean).length;
  const total = document.getElementById('hostCount').dataset.total || Object.keys(status.hosts || {}).length;
  document.getElementById('hostCount').textContent = `${found}/${total}`;
  document.getElementById('liveStatus').innerHTML = status.ovs_bridge
    ? '<span class="status-up">● OVS SDN đang hoạt động</span>'
    : '<span class="status-down">● Chưa thấy OVS SDN</span>';
}
async function loadFlows() {
  const payload = await api('/api/flows');
  const flows = payload.flows || [];
  document.getElementById('flowRows').innerHTML = flows.length ? flows.map((flow) => `
    <tr><td>${flow.switch}</td><td>${flow.source}</td><td>${flow.destination}</td>
    <td><span class="badge ${flow.action === 'ALLOW' ? 'allow' : 'drop'}">${flow.action === 'ALLOW' ? 'CHO PHÉP' : flow.action}</span></td>
    <td>${flow.priority}</td><td>${flow.raw_match}</td><td>${flow.raw_action}</td>
    <td>${flow.packets}</td><td>${flow.bytes}</td><td>${flow.reason}</td></tr>`).join('')
    : '<tr><td colspan="10">Chưa đọc được flow. Hãy kiểm tra 8 OVS và quyền chạy dashboard.</td></tr>';
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
async function runClusterDetail() {
  setBusy(true);
  const body = {
    cluster: document.getElementById('cluster').value,
    seconds: Number(document.getElementById('clusterSeconds').value || 3),
  };
  const output = document.getElementById('clusterOutput');
  output.innerHTML = '<p>Đang chạy test chi tiết từ Mininet...</p>';
  try {
    const payload = await post('/api/test/cluster-detail', body);
    output.innerHTML = `
      <div class="result ${payload.ok ? 'ok' : 'bad'}">
        <strong>${payload.message}</strong>
        <p>${payload.softphone_note}</p>
        ${(payload.cases || []).map((item) => `
          <div style="border-left:4px solid ${item.passed ? '#087f5b' : '#c92a2a'};background:#fff;margin-top:6px;padding:7px;border-radius:6px">
            <strong>${item.passed ? 'PASS' : 'FAIL'} · ${item.name}</strong>
            <p>${item.expected.toUpperCase()} · RTT ${item.rtt_ms ?? '--'} ms · Jitter ${item.jitter_ms ?? '--'} ms · Loss ${item.loss_percent ?? '--'}% · MOS ${item.mos ?? '--'} · TCP ${item.throughput_mbps ?? '--'} Mbps</p>
          </div>`).join('')}
      </div>`;
    await loadFlows();
  } catch (error) {
    output.innerHTML = `<div class="result bad"><strong>Lỗi test chi tiết</strong><p>${error.message}</p></div>`;
  } finally {
    setBusy(false);
  }
}
function initPolicyMap() {
  Object.keys(pingPolicies).forEach((nodeId) => {
    const node = document.getElementById(nodeId);
    if (!node) return;
    node.classList.add('selectable');
    node.addEventListener('click', () => selectPolicyNode(nodeId));
  });
  selectPolicyNode('project_a');
}
async function refreshAll() { clearPath(); await loadTopology(); await loadStatus(); await loadFlows(); initPolicyMap(); }
refreshAll().catch((error) => show('Lỗi dashboard', { ok: false, raw: error.message }));
</script>
</body>
</html>
"""
