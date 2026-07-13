import { RotateCcw, Unplug } from "lucide-react";
import { useMemo, useState } from "react";
import type { Decision, Host, Link, Topology } from "../api/client";

const positions: Record<string, [number, number]> = {
  project_a: [90, 145], project_b: [90, 225], project_c: [90, 305], it_support: [90, 385], h90: [90, 465],
  access_hq_a: [270, 145], access_hq_b: [270, 225], access_hq_c: [270, 305], access_hq_it: [270, 385], voice_access: [270, 465],
  core_hq: [470, 305], c0: [800, 75],
  telesale: [90, 635], backoffice: [90, 735], access_branch: [270, 685], dist_branch: [470, 685],
  fw_hq: [665, 475], fw_branch: [665, 745],
  ce_hq: [800, 255], mpls_cloud: [900, 455], ce_branch: [800, 650],
  internet: [1085, 620],
  hzalo: [1260, 165], hcall: [1260, 315], hsocial: [1260, 555], hinternet: [1260, 725],
  of_bus: [800, 120], of_hq: [660, 165], of_branch: [915, 165],
};

const routedLinks: Record<string, [number, number][]> = {
  "core_hq-fw_hq": [[470, 305], [565, 305], [565, 475], [665, 475]],
  "fw_hq-internet": [[665, 475], [900, 475], [900, 620], [1085, 620]],
  "dist_branch-fw_branch": [[470, 685], [565, 685], [565, 745], [665, 745]],
  "fw_branch-internet": [[665, 745], [900, 745], [900, 620], [1085, 620]],
};

type Props = {
  topology?: Topology;
  links: Link[];
  decision?: Decision;
  activeIndex: number;
  failedLinks: string[];
  onFail: (linkId: string) => void;
  onRecover: (linkId: string) => void;
  onSource: (value: string) => void;
  onDestination: (value: string) => void;
};

function isPathLink(path: string[], source: string, target: string) {
  return path.some((node, index) => {
    const next = path[index + 1];
    return (node === source && next === target) || (node === target && next === source);
  });
}

function labelMap(topology?: Topology) {
  const labels: Record<string, [string, string]> = {};
  topology?.nodes.forEach((node) => {
    const id = String(node.id);
    const title = String(node.label || id);
    let subtitle = "";
    if (node.type === "user_group") subtitle = `${node.count} users · VLAN ${node.vlan}`;
    else if (node.type === "switch") subtitle = "Open vSwitch";
    else if (node.type === "firewall") subtitle = "Mô phỏng Internet Edge";
    else if (node.type === "wan") subtitle = "WAN transport";
    else if (node.type === "controller") subtitle = "127.0.0.1:6653";
    else if (node.ip) subtitle = String(node.ip);
    labels[id] = [title, subtitle];
  });
  return labels;
}

export default function TopologyCanvas(props: Props) {
  const labels = useMemo(() => labelMap(props.topology), [props.topology]);
  const selectableNodes = useMemo(() => Object.keys(props.topology?.policy_map || {}), [props.topology]);
  const [selectedNode, setSelectedNode] = useState("project_a");
  const selectedPosition = positions[selectedNode];
  const selectedPolicy = props.topology?.policy_map?.[selectedNode];
  const currentNode = props.decision?.path[Math.min(props.activeIndex, Math.max(0, props.decision.path.length - 1))];
  const selectedGroup = props.topology?.groups.find((group) => group.id === selectedNode);
  const nameOf = (id: string) => labels[id]?.[0] || id;

  return (
    <section>
      <div className="section-title">
        <div><h2>Sơ đồ Hybrid MPLS L3VPN + SDN Edge Policy</h2><span>Click nhóm để xem user và quan hệ policy</span></div>
        <div className="link-controls">
          <select id="link-select" aria-label="Chọn liên kết">
            {props.links.filter((link) => link.type !== "control").map((link) => (
              <option value={link.id} key={link.id}>{link.source} ↔ {link.target}</option>
            ))}
          </select>
          <button title="Giả lập lỗi liên kết" onClick={() => props.onFail((document.getElementById("link-select") as HTMLSelectElement).value)}><Unplug size={16} /></button>
          <button title="Khôi phục liên kết" onClick={() => props.onRecover((document.getElementById("link-select") as HTMLSelectElement).value)}><RotateCcw size={16} /></button>
        </div>
      </div>
      <div className="topology-scroll">
        <svg className="topology-svg" viewBox="0 0 1360 820" aria-label="Sơ đồ mạng Hybrid MPLS và SDN">
          <rect className="zone" x="20" y="95" width="705" height="430" /><text className="zone-label" x="35" y="117">TRỤ SỞ CHÍNH HQ</text>
          <rect className="zone" x="20" y="575" width="705" height="220" /><text className="zone-label" x="35" y="597">CHI NHÁNH BRANCH</text>
          <rect className="zone" x="755" y="185" width="285" height="610" /><text className="zone-label" x="770" y="207">WAN / MPLS L3VPN</text>
          <rect className="zone" x="1045" y="95" width="295" height="700" /><text className="zone-label" x="1060" y="117">DỊCH VỤ INTERNET</text>

          {props.links.map((link) => {
            const from = positions[link.source]; const to = positions[link.target];
            if (!from || !to) return null;
            const active = props.decision ? isPathLink(props.decision.path, link.source, link.target) : false;
            const failed = props.failedLinks.includes(link.id);
            const route = routedLinks[link.id];
            const className = `topology-link ${link.type} ${active ? props.decision?.action : ""} ${failed ? "failed" : ""}`;
            if (route) return <polyline key={link.id} points={route.map(([x, y]) => `${x},${y}`).join(" ")} className={className} />;
            return <line key={link.id} x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1]} className={className} />;
          })}

          <line x1={positions.c0[0]} y1={positions.c0[1] + 25} x2={positions.of_bus[0]} y2={positions.of_bus[1]} className="topology-link control" />
          <line x1={positions.of_bus[0]} y1={positions.of_bus[1]} x2={positions.of_hq[0]} y2={positions.of_hq[1]} className="topology-link control" />
          <line x1={positions.of_bus[0]} y1={positions.of_bus[1]} x2={positions.of_branch[0]} y2={positions.of_branch[1]} className="topology-link control" />
          {["access_hq_a", "access_hq_b", "access_hq_c", "access_hq_it", "voice_access", "core_hq"].map((target) => (
            <line key={`of-hq-${target}`} x1={positions.of_hq[0]} y1={positions.of_hq[1]} x2={positions[target][0]} y2={positions[target][1]} className="topology-link control-lite" />
          ))}
          {["access_branch", "dist_branch"].map((target) => (
            <line key={`of-branch-${target}`} x1={positions.of_branch[0]} y1={positions.of_branch[1]} x2={positions[target][0]} y2={positions[target][1]} className="topology-link control-lite" />
          ))}

          {selectedPosition && selectedPolicy?.allow.map((target) => positions[target] ? (
            <line key={`allow-${selectedNode}-${target}`} x1={selectedPosition[0]} y1={selectedPosition[1]} x2={positions[target][0]} y2={positions[target][1]} className="ping-map allow" />
          ) : null)}
          {selectedPosition && selectedPolicy?.deny.map((target) => positions[target] ? (
            <line key={`deny-${selectedNode}-${target}`} x1={selectedPosition[0]} y1={selectedPosition[1]} x2={positions[target][0]} y2={positions[target][1]} className="ping-map deny" />
          ) : null)}

          {[["of_bus", "OpenFlow Control Bus", ""], ["of_hq", "HQ OpenFlow Domain", ""], ["of_branch", "Branch OpenFlow Domain", ""]].map(([id, title, subtitle]) => {
            const [x, y] = positions[id];
            return <g className="topology-node controller" key={id} transform={`translate(${x - 70} ${y - 20})`}><rect width="140" height="40" rx="5" /><text x="70" y="18">{title}</text><text className="node-subtitle" x="70" y="32">{subtitle}</text></g>;
          })}

          {Object.entries(positions).filter(([id]) => labels[id]).map(([id, [x, y]]) => {
            const [title, subtitle] = labels[id];
            const nodeType = String(props.topology?.nodes.find((node) => node.id === id)?.type || "");
            const className = nodeType === "user_group" ? "user" : nodeType === "switch" ? "switch" :
              nodeType === "router" ? "router" : nodeType === "wan" ? "cloud" : nodeType === "firewall" ? "firewall" :
              id === "hsocial" ? "blocked" : nodeType === "controller" ? "controller" : "service";
            const selectable = selectableNodes.includes(id);
            return (
              <g className={`topology-node ${className} ${currentNode === id ? "current" : ""} ${selectedNode === id ? "selected" : ""} ${selectable ? "selectable" : ""}`} key={id}
                transform={`translate(${x - 60} ${y - 25})`} onClick={() => selectable && setSelectedNode(id)}>
                <rect width="120" height="50" rx="5" />
                <text x="60" y="20">{title}</text><text className="node-subtitle" x="60" y="36">{subtitle}</text>
              </g>
            );
          })}
          {props.decision?.action === "deny" && props.decision.blocked_at && positions[props.decision.blocked_at] && (
            <g className="deny-mark" transform={`translate(${positions[props.decision.blocked_at][0]} ${positions[props.decision.blocked_at][1]})`}>
              <line x1="-14" y1="-14" x2="14" y2="14" /><line x1="14" y1="-14" x2="-14" y2="14" />
            </g>
          )}
        </svg>
      </div>
      <div className="legend">
        <span><i className="data" />Data Path</span><span><i className="allow" />Luồng được phép</span>
        <span><i className="deny" />Luồng bị chặn</span><span><i className="control" />OpenFlow Control Path</span>
        <span><i className="mpls" />WAN/MPLS transport</span>
      </div>
      {selectedPolicy && (
        <div className="ping-policy-card">
          <strong>{selectedPolicy.title}</strong>
          <div><span className="ok">Được phép:</span> {selectedPolicy.allow.length ? selectedPolicy.allow.map(nameOf).join(", ") : "Không có luồng chủ động vào nội bộ"}</div>
          <div><span className="bad">Bị chặn:</span> {selectedPolicy.deny.length ? selectedPolicy.deny.map(nameOf).join(", ") : "Không có mục chặn trong phạm vi demo"}</div>
        </div>
      )}
      {selectedGroup && (
        <div className="host-group-panel">
          <strong>{selectedGroup.label} · VLAN {selectedGroup.vlan} · {selectedGroup.subnet}</strong>
          <div className="host-list">
            {selectedGroup.hosts.map((host: Host) => (
              <div key={host.name}>
                <span>{host.label} · {host.name} · {host.ip}</span>
                <button onClick={() => props.onSource(host.name)}>Chọn nguồn</button>
                <button onClick={() => props.onDestination(host.name)}>Chọn đích</button>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
