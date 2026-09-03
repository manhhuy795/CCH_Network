import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, Download, Maximize2, Minimize2, Network, Search, ZoomIn, ZoomOut } from "lucide-react";
import type { Decision, Host, Link, Topology } from "../api/client";
import topologyV7Svg from "../assets/enterprise_logical_topology_v7.svg?raw";
import Drawer from "./ui/Drawer";
import StatusBadge from "./ui/StatusBadge";

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

export type DisplayNode = Record<string, unknown> & {
  id: string;
  label?: string;
  type?: string;
  site?: string;
  hosts?: Host[];
  vlan?: number | string;
  subnet?: string;
  count?: number;
  ip?: string;
};

export type ViewMode = "interactive" | "architecture" | "integrated";

type Hotspot = {
  x: number;
  y: number;
  width: number;
  height: number;
  rx?: number;
  label: string;
  center: [number, number];
  isCircle?: boolean;
};

/** Coordinates mapped directly to the README architecture source (1440 x 900). */
export const V7_HOTSPOTS: Record<string, Hotspot> = {
  c0: { x: 500, y: 82, width: 440, height: 66, rx: 13, label: "OS-Ken SDN Controller", center: [720, 115] },
  project_1: { x: 30, y: 690, width: 110, height: 82, rx: 9, label: "Dự án 1", center: [85, 731] },
  project_2_hq: { x: 150, y: 690, width: 160, height: 82, rx: 9, label: "Dự án 2 · HQ", center: [230, 731] },
  project_3: { x: 320, y: 690, width: 110, height: 82, rx: 9, label: "Dự án 3", center: [375, 731] },
  project_4: { x: 440, y: 690, width: 110, height: 82, rx: 9, label: "Dự án 4", center: [495, 731] },
  it_support: { x: 560, y: 690, width: 150, height: 32, rx: 9, label: "IT Support", center: [635, 706] },
  guest: { x: 560, y: 722, width: 75, height: 50, rx: 9, label: "Guest", center: [597.5, 747] },
  iot_hq: { x: 635, y: 722, width: 75, height: 50, rx: 9, label: "HQ IoT", center: [672.5, 747] },
  hdhcp: { x: 720, y: 690, width: 170, height: 82, rx: 9, label: "Infrastructure / DHCP", center: [805, 731] },
  access_floor1: { x: 50, y: 520, width: 210, height: 60, rx: 10, label: "HQ Access Floor 1", center: [155, 550] },
  access_floor2: { x: 290, y: 520, width: 210, height: 60, rx: 10, label: "HQ Access Floor 2", center: [395, 550] },
  infra_access: { x: 570, y: 520, width: 210, height: 60, rx: 10, label: "Infrastructure Access", center: [675, 550] },
  core_hq: { x: 180, y: 350, width: 240, height: 70, rx: 11, label: "CORE-DIST HQ", center: [300, 385] },
  fw_hq: { x: 80, y: 225, width: 240, height: 53, rx: 10, label: "Firewall HQ", center: [200, 251.5] },
  hcall: { x: 600, y: 225, width: 120, height: 53, rx: 10, label: "Partner CRM", center: [660, 251.5] },
  h90: { x: 720, y: 225, width: 120, height: 53, rx: 10, label: "PBX / Contact Center", center: [780, 251.5] },
  l2vpn_primary: { x: 560, y: 352, width: 320, height: 36, rx: 18, label: "VLAN 93 L2VPN Primary", center: [720, 370] },
  l2vpn_backup: { x: 560, y: 408, width: 320, height: 36, rx: 18, label: "VLAN 93 L2VPN Backup", center: [720, 426] },
  ipsec_l3: { x: 560, y: 293, width: 320, height: 34, rx: 17, label: "IPv4 routed intersite abstraction", center: [720, 310] },
  dist_branch: { x: 1020, y: 350, width: 240, height: 70, rx: 11, label: "CORE-DIST Branch", center: [1140, 385] },
  access_branch: { x: 1060, y: 520, width: 210, height: 60, rx: 10, label: "Branch Access", center: [1165, 550] },
  project_2_branch: { x: 960, y: 690, width: 210, height: 82, rx: 9, label: "Dự án 2 · Branch", center: [1065, 731] },
  iot_branch: { x: 1190, y: 690, width: 210, height: 82, rx: 9, label: "Mạng IoT Branch", center: [1295, 731] },
  fw_telesale: { x: 1120, y: 225, width: 240, height: 53, rx: 10, label: "Firewall Branch", center: [1240, 251.5] },
};

export const positions: Record<string, [number, number]> = Object.fromEntries(
  Object.entries(V7_HOTSPOTS).map(([key, value]) => [key, [value.x, value.y]])
);

export function canonicalProject2(id?: string) {
  if (id === "project_2_hq" || id === "project_2_branch") return "project_2";
  return id || "";
}

export function displayNodes(topology?: Topology): DisplayNode[] {
  const groups = topology?.groups || [];
  return (topology?.nodes || []).flatMap((raw) => {
    const node = raw as DisplayNode;
    const group = groups.find((candidate) => candidate.id === String(node.id));
    const hosts = node.hosts || group?.hosts || [];
    if (String(node.id) !== "project_2") {
      return [{ ...node, id: String(node.id), hosts, count: node.count ?? group?.count ?? hosts.length }];
    }
    const hq = hosts.filter((host) => host.site === "hq");
    const branch = hosts.filter((host) => host.site === "branch");
    return [
      { ...node, id: "project_2_hq", label: "Dự án 2 · HQ", site: "hq", vlan: 93, subnet: "10.10.93.0/24", hosts: hq, count: hq.length || 10 },
      { ...node, id: "project_2_branch", label: "Dự án 2 · Branch", site: "branch", vlan: 93, subnet: "10.10.93.0/24", hosts: branch, count: branch.length || 10 },
    ];
  });
}

export function displayLinks(links: Link[]): Link[] {
  return links.map((link) => {
    let source = link.source;
    let target = link.target;
    if (source === "project_2") source = target === "access_branch" || target === "dist_branch" ? "project_2_branch" : "project_2_hq";
    if (target === "project_2") target = source === "access_branch" || source === "dist_branch" ? "project_2_branch" : "project_2_hq";
    return { ...link, source, target };
  });
}

export function endpointForNode(node: DisplayNode) {
  return node.hosts?.[0]?.name || (String(node.id).startsWith("h") ? String(node.id) : undefined);
}

export function isPrimaryL2Link(link: Link) {
  return (
    (link.source === "ce_hq1" && link.target === "l2vpn_primary") ||
    (link.source === "l2vpn_primary" && link.target === "ce_branch1") ||
    (link.source === "core_hq" && link.target === "ce_hq1") ||
    (link.source === "ce_branch1" && link.target === "dist_branch")
  );
}

export function isBackupLink(link: Link) {
  return ["l2vpn_backup", "ce_hq2", "ce_branch2"].some((id) => link.source === id || link.target === id);
}

function hotspotFor(id?: string | null) {
  if (!id) return undefined;
  return V7_HOTSPOTS[id] || V7_HOTSPOTS[id === "project_2" ? "project_2_hq" : id];
}

function nodeSubtitle(node: DisplayNode) {
  if (node.id === "core_hq") return "Collapsed Core/Distribution HA (HQ)";
  if (node.id === "dist_branch") return "Collapsed Core/Distribution HA (Branch)";
  if (node.id === "fw_hq") return "Firewall HA Cluster (HQ)";
  if (node.id === "fw_telesale") return "Firewall HA Cluster (Branch)";
  if (node.id === "l2vpn_primary") return "VLAN 93 L2VPN Primary (Active)";
  if (node.id === "l2vpn_backup") return "VLAN 93 L2VPN Backup (Standby)";
  if (node.id === "ipsec_l3") return "IPv4 routed intersite abstraction";
  if (node.id === "h90") return "External Partner PBX / Contact Center";
  if (node.id === "hcall") return "External Partner CRM";
  if (node.subnet) return `${node.subnet} · VLAN ${node.vlan ?? "-"}`;
  if (node.ip) return `IP: ${node.ip}`;
  return String(node.type || "Thiết bị mạng");
}

export default function TopologyCanvas({
  topology,
  links,
  flows = [],
  decision,
  activeIndex = 0,
  failedLinks = [],
  liveLinkControl,
  authenticated,
  linkOperation,
  source,
  destination,
  onFail,
  onRecover,
  onSource,
  onDestination,
}: Props) {
  const [selectedNode, setSelectedNode] = useState<DisplayNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<DisplayNode | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [fullscreen, setFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const nodes = useMemo(() => displayNodes(topology), [topology]);
  const visibleLinks = useMemo(() => displayLinks(links), [links]);
  const path = useMemo(() => decision?.path || [], [decision?.path]);
  const l2Controls = useMemo(() => visibleLinks.filter(isPrimaryL2Link), [visibleLinks]);
  const primaryDown = l2Controls.some((link) => failedLinks.includes(link.id) || link.status === "down");
  const backupDown = visibleLinks.filter(isBackupLink).some((link) => failedLinks.includes(link.id) || link.status === "down");

  useEffect(() => {
    if (!topology?.hosts?.length) return;
    const names = new Set(topology.hosts.map((host) => host.name));
    if (source && !names.has(source)) onSource("");
    if (destination && !names.has(destination)) onDestination("");
  }, [topology, source, destination, onSource, onDestination]);

  useEffect(() => {
    const syncFullscreen = () => setFullscreen(document.fullscreenElement === containerRef.current);
    document.addEventListener("fullscreenchange", syncFullscreen);
    return () => document.removeEventListener("fullscreenchange", syncFullscreen);
  }, []);

  const filteredNodeIds = useMemo(() => {
    if (!searchQuery.trim()) return null;
    const query = searchQuery.toLowerCase().trim();
    return new Set(
      nodes
        .filter((node) => [node.label, node.id, node.ip, node.subnet, node.vlan].some((value) => String(value || "").toLowerCase().includes(query)))
        .map((node) => node.id)
    );
  }, [nodes, searchQuery]);

  const activePathPoints = useMemo(
    () => path.map((id) => hotspotFor(id)?.center).filter((point): point is [number, number] => Boolean(point)),
    [path]
  );
  const blockedHotspot = hotspotFor(decision?.blocked_at);
  const currentNodeInPath = decision && activeIndex < path.length ? path[activeIndex] : undefined;
  const nodeFlows = useMemo(() => {
    if (!selectedNode) return [];
    return flows.filter((flow) => flow.switch === selectedNode.id || flow.device === selectedNode.id);
  }, [flows, selectedNode]);

  const [zoom, setZoom] = useState(1);
  const handleZoomIn = () => setZoom((z) => Math.min(2.5, +(z + 0.15).toFixed(2)));
  const handleZoomOut = () => setZoom((z) => Math.max(0.6, +(z - 0.15).toFixed(2)));
  const handleZoomReset = () => setZoom(1);

  const toggleFullscreen = async () => {
    if (!containerRef.current) return;
    if (document.fullscreenElement) await document.exitFullscreen?.();
    else await containerRef.current.requestFullscreen?.();
  };

  return (
    <section ref={containerRef} className={`topology-page fixed-layout ${fullscreen ? "fullscreen" : ""}`} data-testid="topology-canvas">
      <header className="topology-command-header">
        <div className="topology-title-row">
          <span className="topology-header-icon"><Network size={20} /></span>
          <div><h2>Enterprise Full-SDN topology</h2><p>OpenFlow domain: 6 OVS · OS-Ken 1.3 · Outside: Firewall, CE, Internet/Partner services</p></div>
        </div>
        <div className="topology-health-strip" aria-label="Trạng thái kiến trúc mạng">
          <span><i className="online" />Gateway VLAN 93 <strong>HQ · 10.10.93.1</strong></span>
          <span><i className={primaryDown ? "down" : "online"} />VLAN 93 Primary <strong>{primaryDown ? "Degraded" : "Active"}</strong></span>
          <span><i className={backupDown ? "down" : "standby"} />VLAN 93 Backup <strong>{backupDown ? "Down" : "Standby"}</strong></span>
        </div>
      </header>

      <div className="topology-toolbar">
        <div className="topology-search-box">
          <Search size={15} aria-hidden="true" />
          <input type="text" aria-label="Tìm kiếm thiết bị" placeholder="Tìm node, IP, subnet hoặc VLAN" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} />
          {searchQuery && <button type="button" onClick={() => setSearchQuery("")} aria-label="Xóa tìm kiếm">Xóa</button>}
        </div>
        <div className="topology-zoom-tools" aria-label="Điều khiển canvas">
          <button type="button" onClick={handleZoomOut} title="Thu nhỏ (Zoom Out)" aria-label="Thu nhỏ"><ZoomOut size={15} /></button>
          <button type="button" onClick={handleZoomReset} className="zoom-value" title="Đặt lại 100%" aria-label="Đặt lại 100%">{Math.round(zoom * 100)}%</button>
          <button type="button" onClick={handleZoomIn} title="Phóng to (Zoom In)" aria-label="Phóng to"><ZoomIn size={15} /></button>
          <button type="button" onClick={toggleFullscreen} title="Toàn màn hình" aria-label="Toàn màn hình">{fullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}</button>
          <a href="/assets/enterprise_logical_topology_v7.svg" download className="download-link-btn" title="Tải sơ đồ SVG" aria-label="Tải sơ đồ SVG"><Download size={15} /></a>
        </div>
      </div>

      <div className="topology-viewport-container">
        <div className="topology-canvas-stage">
          <div className="topology-interactive-stage" style={{ transform: `scale(${zoom})`, transformOrigin: "center center", transition: "transform 0.12s ease-out" }}>
            <div className="topology-vector-underlay" dangerouslySetInnerHTML={{ __html: topologyV7Svg }} />
            <svg viewBox="0 0 1440 900" className="topology-overlay-svg" aria-label="CCH Enterprise Full-SDN topology canvas">
              {activePathPoints.length > 1 && (
                <g className="active-path-glow-layer">
                  <polyline points={activePathPoints.map((point) => point.join(",")).join(" ")} className="packet-trail-halo" />
                  <polyline points={activePathPoints.map((point) => point.join(",")).join(" ")} className="packet-trail-pulse" />
                  <circle r="8" className="packet-dot"><animateMotion path={`M ${activePathPoints.map((point) => point.join(" ")).join(" L ")}`} dur="2s" repeatCount="indefinite" /></circle>
                </g>
              )}
              {blockedHotspot && (
                <g data-testid="blocked-at" className="deny-mark-animated" transform={`translate(${blockedHotspot.center.join(",")})`}>
                  <circle r="30" /><rect x="-44" y="-13" width="88" height="26" rx="4" /><text y="4" textAnchor="middle">BLOCKED</text>
                </g>
              )}
              {nodes.map((node) => {
                const hotspot = hotspotFor(node.id);
                if (!hotspot) return null;
                const endpoint = endpointForNode(node);
                const isSource = source === endpoint;
                const isDestination = destination === endpoint;
                const selected = isSource || isDestination;
                const current = node.id === currentNodeInPath || canonicalProject2(node.id) === currentNodeInPath;
                const blocked = node.id === decision?.blocked_at || canonicalProject2(node.id) === decision?.blocked_at;
                const dimmed = Boolean(filteredNodeIds && !filteredNodeIds.has(node.id));
                const selectNode = () => {
                  if (!endpoint) {
                    setSelectedNode(node);
                    return;
                  }
                  if (source === endpoint) {
                    onSource("");
                    return;
                  }
                  if (destination === endpoint) {
                    onDestination("");
                    return;
                  }
                  if (!source) onSource(endpoint);
                  else onDestination(endpoint);
                };
                return (
                  <g key={node.id} transform={`translate(${hotspot.x},${hotspot.y})`}
                    className={`topology-node-hotspot${dimmed ? " dimmed" : ""}${current ? " current" : ""}${selected ? " selected" : ""}${blocked ? " blocked" : ""}`}
                    role="button" aria-label={`Node ${String(node.label || node.id)}`} tabIndex={0} onClick={selectNode}
                    onMouseEnter={() => setHoveredNode(node)} onMouseLeave={() => setHoveredNode(null)}
                    onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") selectNode(); }}>
                    <title>{hotspot.label}</title>
                    {hotspot.isCircle
                      ? <circle cx={hotspot.width / 2} cy={hotspot.height / 2} r={hotspot.width / 2 + 4} className="hotspot-hitbox" />
                      : <rect width={hotspot.width} height={hotspot.height} rx={hotspot.rx || 6} className="hotspot-hitbox" />}
                    {isSource && <g className="endpoint-badge source" transform={`translate(${Math.max(2, hotspot.width - 64)},-9)`}><rect width="62" height="20" rx="4" /><text x="31" y="14" textAnchor="middle">NGUỒN</text></g>}
                    {isDestination && <g className="endpoint-badge destination" transform={`translate(${Math.max(2, hotspot.width - 54)},-9)`}><rect width="52" height="20" rx="4" /><text x="26" y="14" textAnchor="middle">ĐÍCH</text></g>}
                  </g>
                );
              })}
            </svg>
          </div>
        </div>
        <div className="topology-canvas-caption"><span><i className="hq" />HQ</span><b>VLAN 93 L2VPN Primary / Backup</b><span>Branch<i className="branch" /></span></div>
        {hoveredNode && (
          <div className="topology-quick-tooltip" role="tooltip">
            <span className="tooltip-kicker">{String(hoveredNode.site || hoveredNode.type || "network node")}</span>
            <strong>{String(hoveredNode.label || hoveredNode.id)}</strong><span>{nodeSubtitle(hoveredNode)}</span>
            {hoveredNode.count != null && <small>{hoveredNode.count} thiết bị</small>}
          </div>
        )}
      </div>

      {liveLinkControl && authenticated && l2Controls.length > 0 && (
        <div className="topology-live-controls-card">
          <div className="controls-card-header">
            <div><Activity size={16} /><span><strong>Mininet runtime</strong> · Điều khiển VLAN 93 Primary attachment path</span></div>
            {linkOperation && <span className={`operation-pill ${linkOperation.status}`}>{linkOperation.message}</span>}
          </div>
          <div className="link-buttons-row">
            {l2Controls.map((link) => {
              const down = failedLinks.includes(link.id) || link.status === "down";
              return (
                <div key={link.id} className={`link-ctrl-item ${down ? "down" : "up"}`}>
                  <div className="link-meta"><span className="link-title">{link.source} <b>→</b> {link.target}</span><span className="link-state"><i />{down ? "Down" : "Active"}</span></div>
                  <button
                    type="button"
                    className={down ? "recover-btn" : "fail-btn"}
                    aria-label={down ? `Khôi phục Primary · ${link.source} ↔ ${link.target}` : `Ngắt thử nghiệm Primary · ${link.source} ↔ ${link.target}`}
                    onClick={() => down ? onRecover(link.id) : onFail(link.id)}
                  >
                    {down ? "Khôi phục liên kết" : "Ngắt liên kết"}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <footer className="topology-v7-legend" aria-label="Chú thích Enterprise Full-SDN">
        <span><i className="legend-line vlan" /><strong>VLAN 93</strong> Gateway duy nhất tại HQ</span>
        <span><i className="legend-line mpls" /><strong>MPLS L2VPN</strong> Primary / Backup</span>
        <span><i className="legend-line ipsec" /><strong>IPv4 routed abstraction</strong> Qua firewall boundaries</span>
        <span><i className="legend-line partner" /><strong>Partner PBX/CRM</strong> External service zone</span>
      </footer>

      <Drawer open={Boolean(selectedNode)} onClose={() => setSelectedNode(null)} title={`Chi tiết Node · ${selectedNode?.id || ""}`}>
        {selectedNode && (
          <div className="node-inspector-content">
            <div className="drawer-hero-card">
              <h3>{String(selectedNode.label || selectedNode.id)}</h3><p>{nodeSubtitle(selectedNode)}</p>
              <div className="status-row"><StatusBadge status="online" label="Sẵn sàng" />{selectedNode.site && <span className="site-pill">{String(selectedNode.site).toUpperCase()}</span>}</div>
            </div>
            <dl>
              <dt>Tên thiết bị / Group</dt><dd>{String(selectedNode.id)}</dd>
              <dt>Nhãn hiển thị</dt><dd>{String(selectedNode.label || selectedNode.id)}</dd>
              <dt>Phân loại</dt><dd>{String(selectedNode.type || "device")}</dd>
              <dt>Mô tả vai trò</dt><dd>{nodeSubtitle(selectedNode)}</dd>
              <dt>Site</dt><dd>{String(selectedNode.site || "HQ").toUpperCase()}</dd>
              {selectedNode.vlan != null && <><dt>VLAN</dt><dd>VLAN {String(selectedNode.vlan)}</dd></>}
              {selectedNode.subnet && <><dt>Subnet</dt><dd>{selectedNode.subnet}</dd></>}
              {selectedNode.ip && <><dt>IP Address</dt><dd>{selectedNode.ip}</dd></>}
              <dt>Số lượng Flow</dt><dd>{nodeFlows.length} flows</dd>
            </dl>
            {selectedNode.hosts && selectedNode.hosts.length > 0 && (
              <div className="drawer-hosts-section">
                <h4>Endpoints ({selectedNode.hosts.length})</h4>
                <div className="host-chips-grid">
                  {selectedNode.hosts.map((host) => (
                    <div key={host.name} className={`host-chip ${source === host.name ? "src" : destination === host.name ? "dst" : ""}`}>
                      <div className="chip-info"><span className="host-name">{host.name}</span><span className="host-ip">{host.ip}</span></div>
                      <div className="chip-actions">
                        <button type="button" className={`mini-btn ${source === host.name ? "active" : ""}`} onClick={() => onSource(host.name)}>Nguồn</button>
                        <button type="button" className={`mini-btn ${destination === host.name ? "active" : ""}`} onClick={() => onDestination(host.name)}>Đích</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </section>
  );
}
