import { Focus, Layers3, Maximize2, RotateCcw, Search, Unplug, ZoomIn, ZoomOut } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import type { Decision, Host, Link, Topology } from "../api/client";
import ConfirmDialog from "./ui/ConfirmDialog";
import Drawer from "./ui/Drawer";
import StatusBadge from "./ui/StatusBadge";
import { animationPath } from "./packetPath";

const positions: Record<string, [number, number]> = {
  project_a: [90, 150], project_b: [90, 230], iot_hq: [90, 310], guest: [90, 390],
  project_c_hq: [90, 480], backoffice: [90, 560], it_support: [90, 640],
  access_floor1: [280, 270], access_floor2: [280, 560], dist_hq_1: [470, 270], dist_hq_2: [470, 560],
  core_hq: [650, 420], infra_access: [650, 180], h90: [830, 135],
  hdhcp: [830, 195], hdns: [830, 255], hntp: [830, 315], hmonitor: [830, 375], hnvr: [830, 435],
  hrecording: [830, 495], hdialer: [830, 555], hbackup: [830, 615], had: [830, 675], fw_hq: [830, 735],
  project_c_branch: [90, 800], telesale: [90, 880], iot_branch: [90, 960],
  access_branch: [300, 880], dist_branch: [500, 880], fw_telesale: [800, 960],
  c0: [800, 50], ce_hq: [1020, 250], mpls_primary: [1030, 410], mpls_backup: [1170, 510],
  l2vpn_vpws40: [1100, 700], ce_telesale: [1020, 890], internet_zone: [1360, 620],
  hzalo: [1500, 280], hcall: [1500, 450], hsocial: [1500, 620], hinternet: [1500, 790],
};

const routedLinks: Record<string, [number, number][]> = {
  "core_hq-fw_hq": [[650, 420], [740, 420], [740, 735], [830, 735]],
  "fw_hq-internet_zone": [[830, 735], [1220, 735], [1220, 620], [1360, 620]],
  "dist_branch-fw_telesale": [[500, 880], [650, 880], [650, 960], [800, 960]],
  "fw_telesale-internet_zone": [[800, 960], [1240, 960], [1240, 620], [1360, 620]],
  "dist_hq_2-l2vpn_vpws40:hq-ac": [[470, 560], [760, 560], [760, 250], [1020, 250]],
  "dist_hq_2-l2vpn_vpws40:hq-carrier": [[1020, 250], [1130, 250], [1130, 700], [1100, 700]],
  "l2vpn_vpws40-dist_branch:branch-carrier": [[1100, 700], [1130, 700], [1130, 890], [1020, 890]],
  "l2vpn_vpws40-dist_branch:branch-ac": [[1020, 890], [760, 840], [500, 840], [500, 880]],
};

const regions: Record<string, string> = {
  project_a: "hq", project_b: "hq", project_c_hq: "hq", it_support: "hq", backoffice: "hq", iot_hq: "hq", guest: "hq", h90: "hq",
  access_floor1: "hq", access_floor2: "hq", dist_hq_1: "hq", dist_hq_2: "hq", infra_access: "hq", core_hq: "hq", fw_hq: "hq", ce_hq: "hq", c0: "control",
  hdhcp: "hq", hdns: "hq", hntp: "hq", hmonitor: "hq", hnvr: "hq", hrecording: "hq", hdialer: "hq", hbackup: "hq", had: "hq",
  project_c_branch: "telesale", iot_branch: "telesale", telesale: "telesale", access_branch: "telesale", dist_branch: "telesale", fw_telesale: "telesale", ce_telesale: "telesale",
  mpls_primary: "wan", mpls_backup: "wan", l2vpn_vpws40: "wan",
  internet_zone: "services", hzalo: "services", hcall: "services", hsocial: "services", hinternet: "services",
};

type Inspector = { kind: "node"; id: string } | { kind: "link"; id: string } | null;

type Props = {
  topology?: Topology;
  links: Link[];
  flows?: Array<Record<string, unknown>>;
  metrics?: Record<string, number | string | boolean | object | null>;
  decision?: Decision;
  activeIndex: number;
  failedLinks: string[];
  liveLinkControl: boolean;
  authenticated?: boolean;
  linkOperation?: { linkId: string; action: "fail" | "recover"; status: "running" | "success" | "failed"; message: string };
  source: string;
  destination: string;
  onFail: (linkId: string) => void;
  onRecover: (linkId: string) => void;
  onSource: (value: string) => void;
  onDestination: (value: string) => void;
};

function canonicalNodeId(id: string) {
  return id === "project_c_hq" || id === "project_c_branch" ? "project_c" : id;
}

function isPathLink(path: string[], source: string, target: string) {
  const canonicalSource = canonicalNodeId(source);
  const canonicalTarget = canonicalNodeId(target);
  return path.some((node, index) => {
    const next = path[index + 1];
    return (node === canonicalSource && next === canonicalTarget) || (node === canonicalTarget && next === canonicalSource);
  });
}

function displayNodes(topology?: Topology) {
  return (topology?.nodes || []).flatMap((node) => {
    if (String(node.id) !== "project_c") return [node];
    const hosts = topology?.groups.find((group) => group.id === "project_c")?.hosts || [];
    const atSite = (site: "hq" | "telesale") => hosts.filter((host) => host.site === site);
    return [
      { ...node, id: "project_c_hq", canonical_id: "project_c", label: "Project C · HQ", site: "hq", count: atSite("hq").length, hosts: atSite("hq") },
      { ...node, id: "project_c_branch", canonical_id: "project_c", label: "Project C · Branch", site: "telesale", count: atSite("telesale").length, hosts: atSite("telesale") },
    ];
  });
}

function displayLinks(links: Link[]) {
  const siteAwareLinks = links.map((link) => {
    const projectCEndpoint = link.source === "project_c" ? "source" : link.target === "project_c" ? "target" : undefined;
    if (!projectCEndpoint) return link;
    const peer = projectCEndpoint === "source" ? link.target : link.source;
    return { ...link, [projectCEndpoint]: peer === "access_branch" ? "project_c_branch" : "project_c_hq" };
  });
  return siteAwareLinks.flatMap((link) => {
    const endpoints = new Set([link.source, link.target]);
    if (endpoints.has("dist_hq_2") && endpoints.has("l2vpn_vpws40")) {
      return [
        { ...link, id: `${link.id}:hq-ac`, source: "dist_hq_2", target: "ce_hq", runtime_link_id: link.id, presentation_only: true },
        { ...link, id: `${link.id}:hq-carrier`, source: "ce_hq", target: "l2vpn_vpws40", runtime_link_id: link.id, presentation_only: true },
      ];
    }
    if (endpoints.has("dist_branch") && endpoints.has("l2vpn_vpws40")) {
      return [
        { ...link, id: `${link.id}:branch-carrier`, source: "l2vpn_vpws40", target: "ce_telesale", runtime_link_id: link.id, presentation_only: true },
        { ...link, id: `${link.id}:branch-ac`, source: "ce_telesale", target: "dist_branch", runtime_link_id: link.id, presentation_only: true },
      ];
    }
    return [link];
  });
}

function displayNodeTitle(node: Record<string, unknown>) {
  if (String(node.type || "") === "firewall") {
    const site = String(node.site || "").toLowerCase();
    return site.includes("telesale") ? "Firewall Telesale" : "Firewall HQ";
  }
  return String(node.label || node.id);
}

function wrapNodeText(value: string, maxChars = 17, maxLines = 2) {
  const words = value.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return [""];
  const lines: string[] = [];
  let line = "";
  for (const word of words) {
    if (word.length > maxChars && !line) {
      lines.push(`${word.slice(0, Math.max(1, maxChars - 3))}...`);
      continue;
    }
    const candidate = line ? `${line} ${word}` : word;
    if (candidate.length <= maxChars || !line) line = candidate;
    else {
      lines.push(line);
      line = word;
    }
  }
  if (line) lines.push(line);
  if (lines.length <= maxLines) return lines;
  const visible = lines.slice(0, maxLines);
  const last = visible[maxLines - 1];
  visible[maxLines - 1] = `${last.slice(0, Math.max(1, maxChars - 3))}...`;
  return visible;
}

function labelMap(nodes: Array<Record<string, unknown>>) {
  const labels: Record<string, [string, string]> = {};
  nodes.forEach((node) => {
    const id = String(node.id);
    const title = displayNodeTitle(node);
    let subtitle = "";
    if (node.subtitle) subtitle = String(node.subtitle);
    else if (node.type === "user_group") subtitle = `${node.count} users · VLAN ${node.vlan}`;
    else if (node.type === "endpoint_group") subtitle = `${node.count} endpoints · VLAN ${node.vlan}`;
    else if (node.type === "switch") subtitle = "Open vSwitch";
    else if (node.type === "firewall") subtitle = "nftables - Internet breakout";
    else if (node.type === "wan") subtitle = "WAN transport";
    else if (node.type === "l2vpn") subtitle = "VPWS logic · VLAN 40";
    else if (node.type === "controller") subtitle = "127.0.0.1:6653";
    else if (node.ip) subtitle = String(node.ip);
    labels[id] = [title, subtitle];
  });
  return labels;
}

function nodeClass(type: string, id: string) {
  if (type === "user_group" || type === "endpoint_group") return "user";
  if (type === "switch") return "switch";
  if (type === "router") return "router";
  if (type === "wan") return "cloud";
  if (type === "l2vpn") return "cloud";
  if (type === "firewall") return "firewall";
  if (type === "controller") return "controller";
  if (id === "hsocial") return "blocked";
  return "service";
}

function formatDesignValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "Chưa khai báo";
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDesignState(value: unknown) {
  const state = String(value || "").toLowerCase();
  if (state === "active") return "Đang hoạt động";
  if (state === "standby") return "Dự phòng";
  if (state === "design_only" || state === "design_only_not_simulated") return "Chỉ có trong thiết kế";
  if (state === "runtime_namespace") return "Namespace runtime";
  if (state === "collapsed_voice_placeholder") return "Placeholder voice trong lab";
  return formatDesignValue(value);
}

function DesignOnlyBadge() {
  return <StatusBadge status="unknown" label="Design-only · không phải runtime" />;
}

function TopologyDesignContract({ topology }: { topology: Topology }) {
  const contract = topology.topology_contract;
  if (!contract) return null;

  const circuits = Object.entries(contract.provider_domain.circuits);
  const handoffs = Object.entries(contract.provider_handoff_paths);
  const firewalls = Object.entries(contract.firewall_redundancy);
  const serverComponents = Object.entries(contract.server_zone.components);
  const designNodes = topology.design_nodes || contract.design_nodes;

  return (
    <section className="topology-contract" data-testid="topology-design-contract" aria-label="Thiết kế logic từ Source of Truth">
      <div className="topology-contract-heading">
        <div>
          <h3>Thiết kế logic từ Source of Truth</h3>
          <p>{contract.runtime_authority}. Các đối tượng dưới đây chỉ mô tả thiết kế doanh nghiệp.</p>
        </div>
        <DesignOnlyBadge />
      </div>
      <div className="topology-contract-grid">
        <article className="topology-contract-card">
          <h4>{contract.provider_domain.label}</h4>
          <p className="topology-contract-muted">{contract.provider_domain.handoff_layer}</p>
          <div className="topology-contract-list">
            {circuits.map(([key, circuit]) => (
              <div className="topology-contract-row" key={circuit.id || key}>
                <span className={`circuit-dot ${circuit.color}`} aria-hidden="true" />
                <div><strong>{circuit.label}</strong><small>{formatDesignState(circuit.state)} · {circuit.sites.join(" + ")}</small></div>
              </div>
            ))}
          </div>
        </article>
        <article className="topology-contract-card">
          <h4>WAN handoff</h4>
          <p className="topology-contract-muted">Ánh xạ từ carrier tới firewall từng site</p>
          <div className="topology-contract-list">
            {handoffs.map(([key, handoff]) => (
              <div className="topology-contract-row" key={handoff.handoff_id || key}>
                <span className={`circuit-dot ${handoff.color}`} aria-hidden="true" />
                <div><strong>{handoff.label}</strong><small>{formatDesignState(handoff.state)} · {Object.entries(handoff.site_firewalls).map(([site, mapping]) => `${site}: ${mapping.firewall}`).join(" · ")}</small></div>
              </div>
            ))}
          </div>
        </article>
        <article className="topology-contract-card">
          <h4>Firewall redundancy</h4>
          <p className="topology-contract-muted">Peer HA là design metadata; firewall màu xanh trong SVG là namespace runtime.</p>
          <div className="topology-contract-list">
            {firewalls.map(([site, firewall]) => (
              <div className="topology-contract-row" key={site}>
                <div><strong>{formatDesignValue(site)} · {firewall.runtime_node}</strong><small>{formatDesignValue(firewall.design_role)} · inside {firewall.inside_node} · {firewall.outside_circuits.join(" + ")}</small></div>
                {firewall.design_members?.length ? <small>HA members: {firewall.design_members.join(", ")}</small> : <small>Simulation: single namespace</small>}
              </div>
            ))}
          </div>
        </article>
        <article className="topology-contract-card">
          <h4>Server-zone roles</h4>
          <p className="topology-contract-muted">Switch runtime: {contract.server_zone.runtime_switch}</p>
          <div className="topology-contract-list" data-testid="design-server-zone-list">
            {serverComponents.map(([name, component]) => (
              <div className="topology-contract-row" key={name}>
                <div><strong>{formatDesignValue(name)}</strong><small>runtime: {component.runtime_node || "Không mô phỏng"} · {formatDesignValue(component.design_role || component.runtime_kind || "server zone")}</small></div>
                <small>{formatDesignState(component.runtime_state || (component.runtime_node ? "design_only" : "design_only_not_simulated"))}</small>
              </div>
            ))}
          </div>
        </article>
      </div>
      <div className="topology-contract-footer" data-testid="design-node-list">
        <DesignOnlyBadge />
        <span>{designNodes.length} đối tượng thiết kế không được đưa vào runtime node, packet path hoặc OpenFlow control path.</span>
        <span>Nguồn: {contract.source_of_truth.join(" · ")}</span>
      </div>
    </section>
  );
}

export default function TopologyCanvas(props: Props) {
  const sectionRef = useRef<HTMLElement>(null);
  const renderedNodes = useMemo(() => displayNodes(props.topology), [props.topology]);
  const renderedLinks = useMemo(() => displayLinks(props.links), [props.links]);
  const labels = useMemo(() => labelMap(renderedNodes), [renderedNodes]);
  const [zoom, setZoom] = useState(1);
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState("all");
  const [mode, setMode] = useState<"simple" | "technical">("simple");
  const [legendVisible, setLegendVisible] = useState(true);
  const [inspector, setInspector] = useState<Inspector>(null);
  const [confirmLink, setConfirmLink] = useState<{ id: string; action: "fail" | "recover" } | null>(null);

  const packetPath = animationPath(props.decision);
  const currentPathIndex = Math.min(props.activeIndex, Math.max(0, packetPath.length - 1));
  const currentNode = packetPath[currentPathIndex];
  const projectCNodeForHost = (hostName: string) => props.topology?.hosts.find((host) => host.name === hostName)?.site === "telesale" ? "project_c_branch" : "project_c_hq";
  const currentDisplayNode = currentNode === "project_c"
    ? projectCNodeForHost(currentPathIndex === packetPath.length - 1 ? props.destination : props.source)
    : currentNode;
  const controlledNodes = useMemo(
    () => renderedNodes.filter((node) => node.type === "switch" && positions[String(node.id)]),
    [renderedNodes],
  );
  const selectedNode = inspector?.kind === "node"
    ? renderedNodes.find((node) => String(node.id) === inspector.id)
    : undefined;
  const selectedLink = inspector?.kind === "link"
    ? renderedLinks.find((link) => link.id === inspector.id)
    : undefined;
  const selectedGroup = selectedNode
    ? props.topology?.groups.find((group) => group.id === canonicalNodeId(String(selectedNode.id)))
    : undefined;
  const selectedGroupHosts = selectedGroup && String(selectedNode?.id).startsWith("project_c_")
    ? selectedGroup.hosts.filter((host) => host.site === selectedNode?.site)
    : selectedGroup?.hosts || [];
  const matchingNodes = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return new Set<string>();
    return new Set(renderedNodes
      .filter((node) => JSON.stringify(node).toLowerCase().includes(needle))
      .map((node) => String(node.id)));
  }, [renderedNodes, query]);

  const nodeVisible = (id: string) => region === "all" || regions[id] === region || (region === "hq" && id === "c0");
  const flowForNode = selectedNode
    ? (props.flows || []).filter((flow) => String(flow.switch || "") === String(selectedNode.id))
    : [];
  const nodeTraffic = flowForNode.reduce((sum, flow) => sum + Number(flow.bytes || 0), 0);
  const relatedLinks = selectedNode
    ? renderedLinks.filter((link) => link.source === selectedNode.id || link.target === selectedNode.id)
    : [];
  const linkStatus = selectedLink
    ? (props.failedLinks.includes(selectedLink.runtime_link_id || selectedLink.id) || selectedLink.status === "down" ? "offline" : selectedLink.status === "degraded" ? "degraded" : "online")
    : "unknown";
  const selectedRuntimeLinkId = selectedLink?.runtime_link_id || selectedLink?.id;
  const selectedLinkOperation = selectedLink && props.linkOperation?.linkId === selectedRuntimeLinkId ? props.linkOperation : undefined;

  const chooseEndpoint = (kind: "source" | "destination") => {
    if (!selectedNode) return;
    const endpoint = selectedGroupHosts[0]?.name || canonicalNodeId(String(selectedNode.id));
    if (kind === "source") props.onSource(endpoint);
    else props.onDestination(endpoint);
  };

  return (
    <section ref={sectionRef} className={`topology-workspace ${mode}`}>
      <div className="section-title topology-title">
        <div><h2>Topology mạng Call Center BPO</h2><span>Data path và OpenFlow control path được tách riêng</span></div>
        <div className="topology-toolbar">
          <label className="topology-search"><Search size={15} /><input aria-label="Tìm node" placeholder="Tìm node, IP, VLAN..." value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          <select aria-label="Lọc vùng" value={region} onChange={(event) => setRegion(event.target.value)}>
            <option value="all">Tất cả vùng</option><option value="hq">HQ</option><option value="wan">MPLS</option>
            <option value="telesale">Telesale</option><option value="services">Internet/Services</option>
          </select>
          <div className="segmented" aria-label="Chế độ hiển thị">
            <button className={mode === "simple" ? "active" : ""} onClick={() => setMode("simple")}>Đơn giản</button>
            <button className={mode === "technical" ? "active" : ""} onClick={() => setMode("technical")}>Kỹ thuật</button>
          </div>
          <button className="icon-button" title="Zoom In" onClick={() => setZoom((value) => Math.min(1.6, value + 0.1))}><ZoomIn size={16} /></button>
          <button className="icon-button" title="Zoom Out" onClick={() => setZoom((value) => Math.max(0.75, value - 0.1))}><ZoomOut size={16} /></button>
          <button className="icon-button" title="Fit View" onClick={() => setZoom(1)}><Focus size={16} /></button>
          <button className="icon-button" title="Reset View" onClick={() => { setZoom(1); setQuery(""); setRegion("all"); setInspector(null); }}><RotateCcw size={16} /></button>
          <button className="icon-button" title="Fullscreen" onClick={() => void sectionRef.current?.requestFullscreen?.()}><Maximize2 size={16} /></button>
          <button className={legendVisible ? "icon-button active" : "icon-button"} title="Legend" onClick={() => setLegendVisible((value) => !value)}><Layers3 size={16} /></button>
        </div>
      </div>
      <div className="topology-scroll">
        <svg className="topology-svg" style={{ width: `${zoom * 100}%` }} viewBox="0 0 1600 1050" aria-label="Sơ đồ mạng ba lớp Call Center BPO">
          <rect className="zone" x="20" y="85" width="900" height="680" /><text className="zone-label" x="35" y="107">HQ · CORE / DISTRIBUTION / ACCESS</text>
          <rect className="zone" x="20" y="785" width="900" height="245" /><text className="zone-label" x="35" y="807">BRANCH TELESALE · ACCESS / DISTRIBUTION</text>
          <rect className="zone" x="950" y="85" width="300" height="945" /><text className="zone-label" x="965" y="107">WAN · MPLS L3 + L2VPN VPWS</text>
          <rect className="zone" x="1280" y="85" width="300" height="945" /><text className="zone-label" x="1295" y="107">INTERNET / SERVICES</text>

          {mode === "technical" && controlledNodes.map((node) => {
            const target = positions[String(node.id)];
            const controller = positions.c0;
            return <line data-testid="control-path" key={`control-${String(node.id)}`} x1={controller[0]} y1={controller[1] + 25} x2={target[0]} y2={target[1]} className="topology-link control" />;
          })}

          {renderedLinks.filter((link) => link.type !== "control").map((link) => {
            const from = positions[link.source];
            const to = positions[link.target];
            if (!from || !to) return null;
            const active = props.decision ? isPathLink(packetPath, link.source, link.target) : false;
            const failed = link.status === "down" || props.failedLinks.includes(link.runtime_link_id || link.id);
            const route = routedLinks[link.id];
            const visible = nodeVisible(link.source) && nodeVisible(link.target);
            const blockedEdge = active && props.decision?.action === "deny" && Boolean(props.decision.blocked_at)
              && (link.source === props.decision?.blocked_at || link.target === props.decision?.blocked_at);
            const activeClass = active ? (blockedEdge ? "deny" : "allow") : "";
            const className = `topology-link data-link ${link.type} ${activeClass} ${failed ? "failed" : ""} ${visible ? "" : "region-hidden"}`;
            const openLink = () => setInspector({ kind: "link", id: link.id });
            const keyboardOpen = (event: React.KeyboardEvent) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                openLink();
              }
            };
            const renderHitSegments = (points: Array<[number, number]>) => points.slice(0, -1).map(([x1, y1], index) => {
              const [x2, y2] = points[index + 1];
              const width = Math.max(Math.abs(x2 - x1), 18);
              const height = Math.max(Math.abs(y2 - y1), 18);
              const x = Math.abs(x2 - x1) < 18 ? (x1 + x2) / 2 - width / 2 : Math.min(x1, x2);
              const y = Math.abs(y2 - y1) < 18 ? (y1 + y2) / 2 - height / 2 : Math.min(y1, y2);
              return <rect key={`${link.id}-hit-${index}`} className="link-hit-segment" x={x} y={y} width={width} height={height} />;
            });
            if (route) {
              const points = route.map(([x, y]) => `${x},${y}`).join(" ");
              return (
                <g key={link.id}>
                  <polyline points={points} className={className} aria-hidden="true" />
                  <g className={`link-hit-target ${visible ? "" : "region-hidden"}`} role="button" tabIndex={0} aria-label={`Link ${link.source} đến ${link.target}`} onClick={openLink} onKeyDown={keyboardOpen}>
                    {renderHitSegments(route)}
                  </g>
                </g>
              );
            }
            return (
              <g key={link.id}>
                <line x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1]} className={className} aria-hidden="true" />
                <g className={`link-hit-target ${visible ? "" : "region-hidden"}`} role="button" tabIndex={0} aria-label={`Link ${link.source} đến ${link.target}`} onClick={openLink} onKeyDown={keyboardOpen}>
                  {renderHitSegments([from, to])}
                </g>
              </g>
            );
          })}

          {Object.entries(positions).filter(([id]) => labels[id]).map(([id, [x, y]]) => {
            const [title, subtitle] = labels[id];
            const titleLines = wrapNodeText(title);
            const subtitleLines = wrapNodeText(subtitle, 20, 1);
            const node = renderedNodes.find((item) => String(item.id) === id);
            const type = String(node?.type || "");
            const matched = matchingNodes.has(id);
            const dimmed = query && !matched;
            return (
              <g
                className={`topology-node ${nodeClass(type, id)} ${currentDisplayNode === id ? "current" : ""} ${dimmed ? "search-dimmed" : ""} ${nodeVisible(id) ? "" : "region-hidden"}`}
                key={id}
                transform={`translate(${x - 60} ${y - 25})`}
                onClick={() => setInspector({ kind: "node", id })}
                role="button"
                aria-label={`Node ${title}`}
              >
                <rect width="120" height="50" rx="5" />
                <text x="60" y={titleLines.length > 1 ? 14 : 20}>
                  {titleLines.map((line, index) => <tspan key={`${id}-title-${index}`} x="60" dy={index === 0 ? 0 : 12}>{line}</tspan>)}
                </text>
                <text className="node-subtitle" x="60" y={titleLines.length > 1 ? 43 : 36}>{subtitleLines[0]}</text>
              </g>
            );
          })}
          {props.decision?.action === "deny" && props.decision.blocked_at && positions[props.decision.blocked_at] && (
            <g className="deny-mark" data-testid="blocked-at" transform={`translate(${positions[props.decision.blocked_at][0]} ${positions[props.decision.blocked_at][1]})`}>
              <line x1="-14" y1="-14" x2="14" y2="14" /><line x1="14" y1="-14" x2="-14" y2="14" />
            </g>
          )}
        </svg>
      </div>
      {legendVisible && (
        <div className="legend">
          <span><i className="data" />Data path</span><span><i className="allow" />ALLOW</span>
          <span><i className="deny" />DENY / link DOWN</span><span><i className="control" />OpenFlow control path</span>
          <span><i className="mpls" />MPLS L3 transport</span>
          <span><i className="l2vpn" />L2VPN VPWS · VLAN 40</span>
        </div>
      )}
      {props.topology && <TopologyDesignContract topology={props.topology} />}
      <div className="topology-explanation">
        <p><strong>Luồng liên chi nhánh routed:</strong> User → Access/Distribution → CE → MPLS L3VPN Logic → CE → Distribution/Access → User. Luồng này không đi qua firewall.</p>
        <p><strong>Project C · VLAN 40:</strong> 10 endpoint HQ + 10 endpoint Branch dùng cùng broadcast domain qua L2VPN VPWS logic; gateway tập trung tại Core HQ.</p>
        <p><strong>Luồng Internet:</strong> User → Firewall nftables tại site → Internet/Service. Firewall chỉ xử lý local Internet breakout, không nằm trên data path MPLS.</p>
      </div>
      <Drawer open={Boolean(inspector)} title={selectedNode ? (String(selectedNode.type) === "firewall" ? labels[String(selectedNode.id)]?.[0] : `Node · ${labels[String(selectedNode.id)]?.[0] || String(selectedNode.id)}`) : selectedLink ? `Link · ${selectedLink.source} → ${selectedLink.target}` : "Inspector"} onClose={() => setInspector(null)}>
        {selectedNode && (
          <div className="inspector-grid">
            <StatusBadge status={currentDisplayNode === selectedNode.id ? "online" : "unknown"} label={currentDisplayNode === selectedNode.id ? "Đang có packet" : "Theo inventory"} />
            <dl>
              <dt>Tên</dt><dd>{String(selectedNode.id)}</dd>
              <dt>Logical ID</dt><dd>{String(selectedNode.logical_name || selectedNode.id)}</dd>
              <dt>Vai trò</dt><dd>{String(selectedNode.type || "unknown")}</dd>
              <dt>Site</dt><dd>{String(selectedNode.site || "N/A")}</dd>
              <dt>IP/Subnet</dt><dd>{String(selectedNode.ip || selectedNode.subnet || "N/A")}</dd>
              <dt>VLAN/Group</dt><dd>{String(selectedNode.vlan || selectedNode.group || "N/A")}</dd>
              <dt>Managed by controller</dt><dd>{selectedNode.type === "switch" ? "Có" : "Không"}</dd>
              <dt>DPID</dt><dd>{String(selectedNode.dpid || "N/A")}</dd>
              <dt>Runtime bridge</dt><dd>{String(selectedNode.runtime_bridge || "N/A")}</dd>
              <dt>Trạng thái</dt><dd>{String(selectedNode.status || "unknown")}</dd>
              <dt>Flow count</dt><dd>{flowForNode.length}</dd>
              <dt>Traffic</dt><dd>{nodeTraffic.toLocaleString("vi-VN")} bytes</dd>
              <dt>Link liên quan</dt><dd>{relatedLinks.length}</dd>
            </dl>
            {selectedGroup && (
              <div className="inspector-hosts">
                <strong>{selectedGroup.label} · {selectedGroup.subnet}</strong>
                {selectedGroupHosts.slice(0, 10).map((host: Host) => <span key={host.name}>{host.name} · {host.ip}</span>)}
              </div>
            )}
            {["user_group", "endpoint_group", "service", "blocked_service"].includes(String(selectedNode.type)) && (
              <div className="drawer-actions">
                <button onClick={() => chooseEndpoint("source")}>Chọn làm nguồn</button>
                <button onClick={() => chooseEndpoint("destination")}>Chọn làm đích</button>
              </div>
            )}
          </div>
        )}
        {selectedLink && (
          <div className="inspector-grid">
            <StatusBadge status={linkStatus} />
            {selectedLinkOperation && (
              <div className="link-operation-state" aria-live="polite">
                <StatusBadge
                  status={selectedLinkOperation.status === "success" ? "online" : selectedLinkOperation.status === "failed" ? "offline" : "degraded"}
                  label={selectedLinkOperation.status === "running" ? "Đang thực hiện" : selectedLinkOperation.status === "success" ? "Thành công" : "Thất bại"}
                />
                <p>{selectedLinkOperation.message}</p>
              </div>
            )}
            <dl>
              <dt>Endpoint A</dt><dd>{selectedLink.source}</dd>
              <dt>Endpoint B</dt><dd>{selectedLink.target}</dd>
              <dt>Loại link</dt><dd>{selectedLink.type}</dd>
              {selectedLink.runtime_link_id && <><dt>Runtime attachment</dt><dd>{selectedLink.runtime_link_id}</dd></>}
              <dt>Bandwidth</dt><dd>{String(selectedLink.bandwidth_mbps || "N/A")} Mbps</dd>
              <dt>Delay</dt><dd>{String(selectedLink.delay_ms || "N/A")} ms</dd>
              <dt>Loss</dt><dd>{String(selectedLink.loss_percent || "N/A")}%</dd>
            </dl>
            {props.liveLinkControl && selectedLink.type !== "control" && (
              <div className="drawer-actions">
                <button className="danger" disabled={!props.authenticated || selectedLinkOperation?.status === "running"} onClick={() => setConfirmLink({ id: selectedRuntimeLinkId || selectedLink.id, action: "fail" })}><Unplug size={15} />Fail link</button>
                <button disabled={!props.authenticated || selectedLinkOperation?.status === "running"} onClick={() => setConfirmLink({ id: selectedRuntimeLinkId || selectedLink.id, action: "recover" })}><RotateCcw size={15} />Recover</button>
              </div>
            )}
          </div>
        )}
      </Drawer>
      <ConfirmDialog
        open={Boolean(confirmLink)}
        title={confirmLink?.action === "fail" ? "Ngắt liên kết Mininet?" : "Khôi phục liên kết?"}
        message={`Tác động: đổi link thật ${confirmLink?.id || ""} sang ${confirmLink?.action === "fail" ? "DOWN" : "UP"} trong Mininet. Ping tiếp theo và packet animation sẽ phải dùng path backend mới; packet không được đi qua link DOWN.`}
        confirmLabel={confirmLink?.action === "fail" ? "Fail link" : "Recover link"}
        danger={confirmLink?.action === "fail"}
        onClose={() => setConfirmLink(null)}
        onConfirm={() => {
          if (!confirmLink) return;
          if (confirmLink.action === "fail") props.onFail(confirmLink.id);
          else props.onRecover(confirmLink.id);
          setConfirmLink(null);
        }}
      />
    </section>
  );
}
