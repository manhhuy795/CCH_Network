import { RotateCcw, Unplug } from "lucide-react";
import { useState } from "react";
import type { Decision, Link } from "../api/client";

const positions: Record<string, [number, number]> = {
  project_a: [90, 145], project_b: [90, 225], project_c: [90, 305], it_support: [90, 385], h90: [90, 465],
  access_hq_a: [270, 145], access_hq_b: [270, 225], access_hq_c: [270, 305], access_hq_it: [270, 385], voice_mgmt: [270, 465],
  core_hq: [470, 305], c0: [780, 80],
  telesale: [90, 635], backoffice: [90, 735], access_branch: [270, 685], dist_branch: [470, 685],
  fw_hq: [670, 475], fw_branch: [670, 745],
  ce_hq: [820, 255], mpls_cloud: [895, 405], ce_branch: [820, 650],
  internet: [1085, 620],
  hzalo: [1260, 165], hcall: [1260, 315], hsocial: [1260, 555], hinternet: [1260, 725],
};

const labels: Record<string, [string, string]> = {
  project_a: ["Dự án A", "20 user · VLAN 20"], project_b: ["Dự án B", "20 user · VLAN 30"],
  project_c: ["Dự án C", "20 user · VLAN 40"], it_support: ["Phòng IT", "4 user · VLAN 70"],
  h90: ["Voice Cluster", "PBX/SBC/SIP-RTP"],
  access_hq_a: ["Access HQ-A", "Open vSwitch"], access_hq_b: ["Access HQ-B", "Open vSwitch"],
  access_hq_c: ["Access HQ-C", "Open vSwitch"], access_hq_it: ["Access HQ-IT", "Open vSwitch"],
  voice_mgmt: ["Voice Access", "Open vSwitch"],
  core_hq: ["HQ Core SDN", "OVS · OpenFlow 1.3"], c0: ["SDN Controller", "127.0.0.1:6653"],
  telesale: ["Telesale", "20 user · VLAN 50"], backoffice: ["BackOffice", "20 user · VLAN 60"],
  access_branch: ["Branch Access", "Open vSwitch"], dist_branch: ["Branch Distribution", "OVS · OpenFlow 1.3"],
  ce_hq: ["CE Router HQ", "Customer Edge"], mpls_cloud: ["MPLS L3VPN Cloud", "ISP quản lý"],
  ce_branch: ["CE Router Branch", "Customer Edge"], fw_hq: ["Firewall HQ", "Internet Edge"],
  fw_branch: ["Firewall Branch", "Internet Edge"], internet: ["Internet Zone", "Service Gateway"],
  hzalo: ["Zalo", "Cho phép"], hcall: ["Call App / CRM", "Cho phép"],
  hsocial: ["Mạng xã hội", "Bị chặn"], hinternet: ["Internet chung", "Kiểm thử"],
};

const controlled = ["access_hq_a", "access_hq_b", "access_hq_c", "access_hq_it", "voice_mgmt", "core_hq", "access_branch", "dist_branch"];

const selectableNodes = ["project_a", "project_b", "project_c", "telesale", "backoffice", "it_support", "h90", "hzalo", "hcall", "hsocial", "hinternet"];

const pingPolicy: Record<string, { title: string; allow: string[]; deny: string[]; note: string }> = {
  project_a: {
    title: "Dự án A / VLAN 20",
    allow: ["h90", "hzalo", "hcall", "hinternet"],
    deny: ["project_b", "project_c", "telesale", "backoffice", "hsocial"],
    note: "Máy agent chạy Cfono/Gphone chỉ đi tới cụm PBX/SBC/SIP-RTP và Call App cần thiết, không mở ngang sang dự án khác.",
  },
  project_b: {
    title: "Dự án B / VLAN 30",
    allow: ["h90", "hzalo", "hcall", "hinternet"],
    deny: ["project_a", "project_c", "telesale", "backoffice", "hsocial"],
    note: "Cách ly với Project A/C; voice đi về PBX/SIP-RTP service.",
  },
  project_c: {
    title: "Dự án C / VLAN 40",
    allow: ["h90", "hzalo", "hcall", "hinternet"],
    deny: ["project_a", "project_b", "telesale", "backoffice", "hsocial"],
    note: "Cách ly với Project A/B; không cho agent ping ngang nhau giữa dự án.",
  },
  telesale: {
    title: "Telesale / VLAN 50",
    allow: ["h90", "hzalo", "hcall", "hinternet"],
    deny: ["project_a", "project_b", "project_c", "backoffice", "hsocial"],
    note: "Không mở full access qua MPLS sang các project HQ; chỉ IT Support có quyền hỗ trợ user.",
  },
  backoffice: {
    title: "BackOffice / VLAN 60",
    allow: ["h90", "hzalo", "hcall", "hinternet"],
    deny: ["telesale", "project_a", "project_b", "project_c", "hsocial"],
    note: "Không có full access sang HQ hoặc Telesale.",
  },
  it_support: {
    title: "IT Support / VLAN 70",
    allow: ["project_a", "project_b", "project_c", "telesale", "backoffice", "h90", "hzalo", "hcall", "hsocial", "hinternet"],
    deny: [],
    note: "IT được full access để hỗ trợ/remote, nhưng Internet bên ngoài vẫn không được chủ động ping vào IT.",
  },
  h90: {
    title: "Voice Cluster cho Cfono/Gphone",
    allow: ["project_a", "project_b", "project_c", "telesale", "backoffice", "it_support"],
    deny: ["hzalo", "hcall", "hsocial", "hinternet"],
    note: "Đây là cụm PBX/SBC/SIP-RTP mô phỏng; không phải mở peer-to-peer giữa agent.",
  },
  hzalo: {
    title: "Zalo Simulator",
    allow: [],
    deny: ["project_a", "project_b", "project_c", "telesale", "backoffice", "it_support"],
    note: "Service ngoài chỉ phản hồi phiên do user khởi tạo, không chủ động ping vào trong.",
  },
  hcall: {
    title: "Call App / CRM",
    allow: [],
    deny: ["project_a", "project_b", "project_c", "telesale", "backoffice", "it_support"],
    note: "Ứng dụng ngoài không được chủ động mở kết nối vào máy agent.",
  },
  hsocial: {
    title: "Mạng xã hội",
    allow: [],
    deny: ["project_a", "project_b", "project_c", "telesale", "backoffice", "it_support"],
    note: "User thường bị chặn truy cập Social; Social cũng không được chủ động ping vào trong.",
  },
  hinternet: {
    title: "Internet bên ngoài",
    allow: [],
    deny: ["project_a", "project_b", "project_c", "telesale", "backoffice", "it_support"],
    note: "Mặc định deny inbound từ Internet vào hệ thống nội bộ.",
  },
};

const names = Object.fromEntries(Object.entries(labels).map(([id, [title]]) => [id, title])) as Record<string, string>;

const routedLinks: Record<string, [number, number][]> = {
  "core_hq-fw_hq": [[470, 305], [565, 305], [565, 475], [670, 475]],
  "fw_hq-internet": [[670, 475], [900, 475], [900, 620], [1085, 620]],
  "dist_branch-fw_branch": [[470, 685], [565, 685], [565, 745], [670, 745]],
  "fw_branch-internet": [[670, 745], [900, 745], [900, 620], [1085, 620]],
};

type Props = {
  links: Link[];
  decision?: Decision;
  activeIndex: number;
  failedLinks: string[];
  onFail: (linkId: string) => void;
  onRecover: (linkId: string) => void;
};

function isPathLink(path: string[], source: string, target: string) {
  return path.some((node, index) => {
    const next = path[index + 1];
    return (node === source && next === target) || (node === target && next === source);
  });
}

export default function TopologyCanvas({ links, decision, activeIndex, failedLinks, onFail, onRecover }: Props) {
  const [selectedNode, setSelectedNode] = useState("project_a");
  const selectedPolicy = pingPolicy[selectedNode];
  const currentNode = decision?.path[Math.min(activeIndex, Math.max(0, decision.path.length - 1))];
  const selectedPosition = positions[selectedNode];
  return (
    <section>
      <div className="section-title">
        <div><h2>Sơ đồ Hybrid MPLS L3VPN + SDN Edge Policy</h2><span>Bấm vào từng cụm để xem được ping / không được ping tới đâu</span></div>
        <div className="link-controls">
          <select id="link-select" aria-label="Chọn liên kết">
            {links.filter((link) => link.type !== "control").map((link) => (
              <option value={link.id} key={link.id}>{link.source} ↔ {link.target}</option>
            ))}
          </select>
          <button title="Giả lập lỗi liên kết" onClick={() => onFail((document.getElementById("link-select") as HTMLSelectElement).value)}><Unplug size={16} /></button>
          <button title="Khôi phục liên kết" onClick={() => onRecover((document.getElementById("link-select") as HTMLSelectElement).value)}><RotateCcw size={16} /></button>
        </div>
      </div>
      <div className="topology-scroll">
        <svg className="topology-svg" viewBox="0 0 1360 820" aria-label="Sơ đồ mạng Hybrid MPLS và SDN">
          <rect className="zone" x="20" y="95" width="700" height="430" /><text className="zone-label" x="35" y="117">TRỤ SỞ CHÍNH · PROJECT / IT / VOICE · FIREWALL HQ TẠI BIÊN INTERNET</text>
          <rect className="zone" x="20" y="575" width="700" height="220" /><text className="zone-label" x="35" y="597">CHI NHÁNH · TELESALE / BACKOFFICE · FIREWALL BRANCH TẠI BIÊN INTERNET</text>
          <rect className="zone" x="755" y="185" width="270" height="610" /><text className="zone-label" x="770" y="207">WAN / MPLS L3VPN</text>
          <rect className="zone" x="1045" y="95" width="295" height="700" /><text className="zone-label" x="1060" y="117">DỊCH VỤ / INTERNET</text>
          <text className="zone-label" x="765" y="725">Liên site: Core/Dist → CE → MPLS → CE</text>
          <text className="zone-label" x="765" y="745">Internet/service: qua Firewall từng site</text>

          {links.map((link) => {
            const from = positions[link.source]; const to = positions[link.target];
            if (!from || !to) return null;
            const active = decision ? isPathLink(decision.path, link.source, link.target) : false;
            const failed = failedLinks.includes(link.id);
            const route = routedLinks[link.id];
            if (route) {
              return <polyline key={link.id} points={route.map(([x, y]) => `${x},${y}`).join(" ")}
                className={`topology-link ${link.type} ${active ? decision?.action : ""} ${failed ? "failed" : ""}`} />;
            }
            return <line key={link.id} x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1]}
              className={`topology-link ${link.type} ${active ? decision?.action : ""} ${failed ? "failed" : ""}`} />;
          })}
          {controlled.map((target) => {
            const from = positions.c0; const to = positions[target];
            return <line key={`control-${target}`} x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1]} className="topology-link control" />;
          })}

          {selectedPosition && selectedPolicy && selectedPolicy.allow.map((target) => positions[target] ? (
            <line key={`allow-${selectedNode}-${target}`} x1={selectedPosition[0]} y1={selectedPosition[1]} x2={positions[target][0]} y2={positions[target][1]} className="ping-map allow" />
          ) : null)}
          {selectedPosition && selectedPolicy && selectedPolicy.deny.map((target) => positions[target] ? (
            <line key={`deny-${selectedNode}-${target}`} x1={selectedPosition[0]} y1={selectedPosition[1]} x2={positions[target][0]} y2={positions[target][1]} className="ping-map deny" />
          ) : null)}

          {Object.entries(positions).map(([id, [x, y]]) => {
            const [title, subtitle] = labels[id];
            const className = ["ce_hq", "ce_branch"].includes(id) ? "router" :
              id === "mpls_cloud" ? "cloud" : id.startsWith("fw_") ? "firewall" :
              ["project_a", "project_b", "project_c", "it_support", "telesale", "backoffice"].includes(id) ? "user" :
              controlled.includes(id) ? "switch" : id === "hsocial" ? "blocked" : id === "c0" ? "controller" : "service";
            const selectable = selectableNodes.includes(id);
            return (
              <g className={`topology-node ${className} ${currentNode === id ? "current" : ""} ${selectedNode === id ? "selected" : ""} ${selectable ? "selectable" : ""}`} key={id}
                transform={`translate(${x - 60} ${y - 25})`} onClick={() => selectable && setSelectedNode(id)}>
                <rect width="120" height="50" rx="5" />
                <text x="60" y="20">{title}</text><text className="node-subtitle" x="60" y="36">{subtitle}</text>
              </g>
            );
          })}
          {decision?.action === "deny" && decision.blocked_at && positions[decision.blocked_at] && (
            <g className="deny-mark" transform={`translate(${positions[decision.blocked_at][0]} ${positions[decision.blocked_at][1]})`}>
              <line x1="-14" y1="-14" x2="14" y2="14" /><line x1="14" y1="-14" x2="-14" y2="14" />
            </g>
          )}
        </svg>
      </div>
      <div className="legend">
        <span><i className="data" />Liên kết dữ liệu</span><span><i className="allow" />Luồng được phép</span>
        <span><i className="deny" />Luồng bị chặn</span><span><i className="control" />Kênh OpenFlow</span>
        <span><i className="mpls" />MPLS L3VPN transport</span>
      </div>
      {selectedPolicy && (
        <div className="ping-policy-card">
          <strong>{selectedPolicy.title}</strong>
          <p>{selectedPolicy.note}</p>
          <div><span className="ok">Được ping:</span> {selectedPolicy.allow.length ? selectedPolicy.allow.map((id) => names[id]).join(", ") : "Không chủ động ping vào nội bộ"}</div>
          <div><span className="bad">Không được ping:</span> {selectedPolicy.deny.length ? selectedPolicy.deny.map((id) => names[id]).join(", ") : "Không có mục chặn trong phạm vi demo"}</div>
        </div>
      )}
    </section>
  );
}
