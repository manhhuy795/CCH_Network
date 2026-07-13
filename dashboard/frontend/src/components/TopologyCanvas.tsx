import { RotateCcw, Unplug } from "lucide-react";
import type { Decision, Link } from "../api/client";

const positions: Record<string, [number, number]> = {
  project_a: [90, 145], project_b: [90, 225], project_c: [90, 305], it_support: [90, 385], h90: [90, 465],
  access_hq_a: [270, 145], access_hq_b: [270, 225], access_hq_c: [270, 305], access_hq_it: [270, 385], voice_mgmt: [270, 465],
  core_hq: [470, 305], c0: [780, 80],
  telesale: [90, 635], backoffice: [90, 735], access_branch: [270, 685], dist_branch: [470, 685],
  fw_hq: [660, 405], fw_branch: [660, 685],
  ce_hq: [780, 305], mpls_cloud: [860, 505], ce_branch: [780, 685],
  internet: [1060, 505],
  hzalo: [1260, 165], hcall: [1260, 315], hsocial: [1260, 555], hinternet: [1260, 725],
};

const labels: Record<string, [string, string]> = {
  project_a: ["Dự án A", "20 user · VLAN 20"], project_b: ["Dự án B", "20 user · VLAN 30"],
  project_c: ["Dự án C", "20 user · VLAN 40"], it_support: ["Phòng IT", "10 user · VLAN 70"],
  h90: ["Voice Service", "VLAN 90"],
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
  const currentNode = decision?.path[Math.min(activeIndex, Math.max(0, decision.path.length - 1))];
  return (
    <section>
      <div className="section-title">
        <div><h2>Sơ đồ Hybrid MPLS L3VPN + SDN Edge Policy</h2><span>110 user được gom thành 6 nhóm, có phòng IT Support</span></div>
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
          <rect className="zone" x="740" y="210" width="245" height="585" /><text className="zone-label" x="755" y="232">WAN / MPLS L3VPN</text>
          <rect className="zone" x="1010" y="95" width="330" height="700" /><text className="zone-label" x="1025" y="117">DỊCH VỤ / INTERNET</text>

          {links.map((link) => {
            const from = positions[link.source]; const to = positions[link.target];
            if (!from || !to) return null;
            const active = decision ? isPathLink(decision.path, link.source, link.target) : false;
            const failed = failedLinks.includes(link.id);
            return <line key={link.id} x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1]}
              className={`topology-link ${link.type} ${active ? decision?.action : ""} ${failed ? "failed" : ""}`} />;
          })}
          {controlled.map((target) => {
            const from = positions.c0; const to = positions[target];
            return <line key={`control-${target}`} x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1]} className="topology-link control" />;
          })}

          {Object.entries(positions).map(([id, [x, y]]) => {
            const [title, subtitle] = labels[id];
            const className = ["ce_hq", "ce_branch"].includes(id) ? "router" :
              id === "mpls_cloud" ? "cloud" : id.startsWith("fw_") ? "firewall" :
              ["project_a", "project_b", "project_c", "it_support", "telesale", "backoffice"].includes(id) ? "user" :
              controlled.includes(id) ? "switch" : id === "hsocial" ? "blocked" : id === "c0" ? "controller" : "service";
            return (
              <g className={`topology-node ${className} ${currentNode === id ? "current" : ""}`} key={id} transform={`translate(${x - 60} ${y - 25})`}>
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
    </section>
  );
}
