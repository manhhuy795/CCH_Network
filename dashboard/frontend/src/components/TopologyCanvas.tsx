import { Maximize2, RotateCcw, Search, Unplug, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Decision, Host, Link, Topology } from "../api/client";

const positions: Record<string, [number, number]> = {
  project_a: [90, 145], project_b: [90, 225], project_c: [90, 305], it_support: [90, 385], h90: [90, 465],
  access_hq_a: [270, 145], access_hq_b: [270, 225], access_hq_c: [270, 305], access_hq_it: [270, 385], voice_access: [270, 465],
  core_hq: [470, 305], c0: [800, 75],
  telesale: [90, 635], backoffice: [90, 735], access_branch: [270, 685], dist_branch: [470, 685],
  fw_hq: [665, 305], fw_branch: [665, 745],
  ce_hq: [800, 255], mpls_cloud: [900, 455], ce_branch: [800, 650],
  internet: [1085, 620],
  hzalo: [1260, 165], hcall: [1260, 315], hsocial: [1260, 555], hinternet: [1260, 725],
  of_bus: [800, 120], of_hq: [660, 165], of_branch: [915, 165],
};

const routedLinks: Record<string, [number, number][]> = {
  "core_hq-fw_hq": [[470, 305], [665, 305]],
  "fw_hq-internet": [[665, 305], [1040, 305], [1040, 620], [1085, 620]],
  "dist_branch-fw_branch": [[470, 685], [565, 685], [565, 745], [665, 745]],
  "fw_branch-internet": [[665, 745], [900, 745], [900, 620], [1085, 620]],
};

type Props = {
  topology?: Topology;
  links: Link[];
  decision?: Decision;
  activeIndex: number;
  failedLinks: string[];
  liveLinkControl: boolean;
  source: string;
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
    if (node.subtitle) subtitle = String(node.subtitle);
    else if (node.type === "user_group") subtitle = `${node.count} users - VLAN ${node.vlan}`;
    else if (node.type === "switch") subtitle = "Open vSwitch";
    else if (node.type === "firewall") subtitle = "Simulated policy boundary";
    else if (node.type === "wan") subtitle = "WAN transport";
    else if (node.type === "controller") subtitle = "127.0.0.1:6653";
    else if (node.ip) subtitle = String(node.ip);
    labels[id] = [title, subtitle];
  });
  return labels;
}

export default function TopologyCanvas(props: Props) {
  const sectionRef = useRef<HTMLElement>(null);
  const labels = useMemo(() => labelMap(props.topology), [props.topology]);
  const selectableNodes = useMemo(() => (props.topology?.nodes || [])
    .filter((node) => ["user_group", "service", "blocked_service"].includes(String(node.type)))
    .map((node) => String(node.id)), [props.topology]);
  const [selectedNode, setSelectedNode] = useState("project_a");
  const [selectedLink, setSelectedLink] = useState("");
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    const sourceHost = props.topology?.hosts.find((host) => host.name === props.source);
    if (sourceHost?.group) setSelectedNode(sourceHost.group);
  }, [props.source, props.topology]);

  useEffect(() => {
    const firstLink = props.links.find((link) => link.type !== "control")?.id || "";
    if (!props.links.some((link) => link.id === selectedLink)) setSelectedLink(firstLink);
  }, [props.links, selectedLink]);

  const currentNode = props.decision?.path[Math.min(props.activeIndex, Math.max(0, props.decision.path.length - 1))];
  const selectedGroup = props.topology?.groups.find((group) => group.id === selectedNode);

  return (
    <section ref={sectionRef}>
      <div className="section-title">
        <div><h2>So do Hybrid MPLS L3VPN + SDN Edge Policy</h2><span>Click cum de xem user va quan he policy</span></div>
        <div className="topology-toolbar">
          <button title="Zoom In" onClick={() => setZoom((value) => Math.min(1.6, value + 0.1))}><ZoomIn size={16} /></button>
          <button title="Zoom Out" onClick={() => setZoom((value) => Math.max(0.75, value - 0.1))}><ZoomOut size={16} /></button>
          <button title="Fit View" onClick={() => setZoom(1)}><Search size={16} /></button>
          <button title="Fullscreen" onClick={() => void sectionRef.current?.requestFullscreen?.()}><Maximize2 size={16} /></button>
          <button title="Reset View" onClick={() => { setZoom(1); setSelectedNode("project_a"); }}><RotateCcw size={16} /></button>
        </div>
        {props.liveLinkControl ? (
          <div className="link-controls">
            <select value={selectedLink} aria-label="Chon lien ket" onChange={(event) => setSelectedLink(event.target.value)}>
              {props.links.filter((link) => link.type !== "control").map((link) => (
                <option value={link.id} key={link.id}>{link.source} - {link.target} ({link.status})</option>
              ))}
            </select>
            <button title="Lam link that trong Mininet bi down" onClick={() => selectedLink && props.onFail(selectedLink)}><Unplug size={16} /></button>
            <button title="Khoi phuc link that trong Mininet" onClick={() => selectedLink && props.onRecover(selectedLink)}><RotateCcw size={16} /></button>
          </div>
        ) : (
          <span className="runtime-hint">Link fail/recover chi bat khi topology Mininet dang chay.</span>
        )}
      </div>
      <div className="topology-scroll">
        <svg className="topology-svg" style={{ width: `${zoom * 100}%` }} viewBox="0 0 1360 820" aria-label="So do mang Hybrid MPLS va SDN">
          <rect className="zone" x="20" y="95" width="705" height="430" /><text className="zone-label" x="35" y="117">TRU SO CHINH HQ</text>
          <rect className="zone" x="20" y="575" width="705" height="220" /><text className="zone-label" x="35" y="597">CHI NHANH BRANCH</text>
          <rect className="zone" x="755" y="185" width="285" height="610" /><text className="zone-label" x="770" y="207">WAN / MPLS L3VPN LOGIC</text>
          <rect className="zone" x="1045" y="95" width="295" height="700" /><text className="zone-label" x="1060" y="117">DICH VU INTERNET</text>

          {props.links.map((link) => {
            const from = positions[link.source];
            const to = positions[link.target];
            if (!from || !to) return null;
            const active = props.decision ? isPathLink(props.decision.path, link.source, link.target) : false;
            const failed = link.status === "down" || props.failedLinks.includes(link.id);
            const route = routedLinks[link.id];
            const className = `topology-link ${link.type} ${active ? props.decision?.action : ""} ${failed ? "failed" : ""}`;
            if (route) return <polyline key={link.id} points={route.map(([x, y]) => `${x},${y}`).join(" ")} className={className} />;
            return <line key={link.id} x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1]} className={className} />;
          })}

          <line x1={positions.c0[0]} y1={positions.c0[1] + 25} x2={positions.of_bus[0]} y2={positions.of_bus[1]} className="topology-link control" />
          <line x1={positions.of_bus[0]} y1={positions.of_bus[1]} x2={positions.of_hq[0]} y2={positions.of_hq[1]} className="topology-link control" />
          <line x1={positions.of_bus[0]} y1={positions.of_bus[1]} x2={positions.of_branch[0]} y2={positions.of_branch[1]} className="topology-link control" />
          <g className="of-domain-list" transform="translate(560 182)">
            <text>HQ OpenFlow Domain</text>
            <text y="16">Access HQ-A · Access HQ-B · Access HQ-C</text>
            <text y="32">Access HQ-IT · Voice Access · HQ Core</text>
          </g>
          <g className="of-domain-list" transform="translate(845 182)">
            <text>Branch OpenFlow Domain</text>
            <text y="16">Branch Access · Branch Distribution</text>
          </g>

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
        <span><i className="data" />Data Path</span><span><i className="allow" />Luong duoc phep</span>
        <span><i className="deny" />Luong bi chan</span><span><i className="control" />OpenFlow Control Path</span>
        <span><i className="mpls" />WAN/MPLS transport</span>
      </div>
      {selectedGroup && (
        <div className="host-group-panel">
          <strong>{selectedGroup.label} - VLAN {selectedGroup.vlan} - {selectedGroup.subnet}</strong>
          <div className="host-list">
            {selectedGroup.hosts.map((host: Host) => (
              <div key={host.name}>
                <span>{host.label} - {host.name} - {host.ip} - status: inventory</span>
                <button onClick={() => props.onSource(host.name)}>Chon nguon</button>
                <button onClick={() => props.onDestination(host.name)}>Chon dich</button>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
