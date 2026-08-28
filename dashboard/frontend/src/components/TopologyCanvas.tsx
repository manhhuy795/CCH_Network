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

/** Coordinates mapped directly to enterprise_logical_topology_v7.svg (1900 x 880). */
export const V7_HOTSPOTS: Record<string, Hotspot> = {
  c0: { x: 860, y: 15, width: 180, height: 45, rx: 6, label: "OS-Ken SDN Controller", center: [950, 38] },
  project_1: { x: 50, y: 665, width: 105, height: 140, rx: 7, label: "Dự án 1", center: [102.5, 735] },
  project_2_hq: { x: 165, y: 665, width: 105, height: 140, rx: 7, label: "Dự án 2 · HQ", center: [217.5, 735] },
  project_3: { x: 280, y: 665, width: 105, height: 140, rx: 7, label: "Dự án 3", center: [332.5, 735] },
  project_4: { x: 395, y: 665, width: 105, height: 140, rx: 7, label: "Dự án 4", center: [447.5, 735] },
  infra_access: { x: 510, y: 665, width: 120, height: 140, rx: 7, label: "Hạ tầng", center: [570, 735] },
  hdhcp: { x: 645, y: 665, width: 125, height: 140, rx: 7, label: "Server Farm / DHCP", center: [707.5, 735] },
  access_floor1: { x: 50, y: 635, width: 220, height: 24, rx: 4, label: "HQ Access A", center: [160, 647] },
  access_floor2: { x: 280, y: 635, width: 220, height: 24, rx: 4, label: "HQ Access B", center: [390, 647] },
  core_hq: { x: 260, y: 345, width: 390, height: 245, rx: 8, label: "CORE-DIST HQ", center: [455, 467] },
  fw_hq: { x: 325, y: 180, width: 300, height: 115, rx: 8, label: "Firewall HQ HA", center: [475, 237] },
  partner: { x: 55, y: 170, width: 165, height: 112, rx: 8, label: "Hệ thống Đối tác", center: [137.5, 226] },
  hcall: { x: 65, y: 205, width: 145, height: 34, rx: 5, label: "Partner CRM", center: [137.5, 222] },
  h90: { x: 65, y: 240, width: 145, height: 34, rx: 5, label: "PBX / Contact Center", center: [137.5, 257] },
  ce_hq1: { x: 712, y: 402, width: 56, height: 56, isCircle: true, label: "CE-HQ1", center: [740, 430] },
  ce_hq2: { x: 712, y: 482, width: 56, height: 56, isCircle: true, label: "CE-HQ2", center: [740, 510] },
  l2vpn_primary: { x: 855, y: 400, width: 190, height: 60, rx: 28, label: "MPLS L2VPN Primary", center: [950, 430] },
  l2vpn_backup: { x: 855, y: 480, width: 190, height: 60, rx: 28, label: "MPLS L2VPN Backup", center: [950, 510] },
  ipsec_l3: { x: 862, y: 207, width: 176, height: 26, rx: 6, label: "IPsec L3 VPN", center: [950, 220] },
  ce_branch1: { x: 1132, y: 402, width: 56, height: 56, isCircle: true, label: "CE-BR1", center: [1160, 430] },
  ce_branch2: { x: 1132, y: 482, width: 56, height: 56, isCircle: true, label: "CE-BR2", center: [1160, 510] },
  dist_branch: { x: 1250, y: 345, width: 390, height: 245, rx: 8, label: "CORE-DIST Branch", center: [1445, 467] },
  access_branch: { x: 1210, y: 635, width: 230, height: 24, rx: 4, label: "Branch Access", center: [1325, 647] },
  project_2_branch: { x: 1210, y: 665, width: 230, height: 155, rx: 8, label: "Dự án 2 · Branch", center: [1325, 742] },
  iot_branch: { x: 1480, y: 665, width: 230, height: 155, rx: 8, label: "Mạng IoT Branch", center: [1595, 742] },
  fw_telesale: { x: 1335, y: 180, width: 300, height: 115, rx: 8, label: "Firewall Branch HA", center: [1485, 237] },
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
  if (node.id === "l2vpn_primary") return "MPLS L2VPN Đường chính (Active)";
  if (node.id === "l2vpn_backup") return "MPLS L2VPN Đường dự phòng (Standby)";
  if (node.id === "ipsec_l3") return "IPsec L3 Routed Overlay (Internet)";
  if (node.id === "h90") return "PBX / Contact Center (VLAN 90)";
  if (node.id === "hcall") return "Partner CRM (VLAN 90)";
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
          <div><h2>Sơ đồ logic mạng doanh nghiệp · v7</h2><p>HQ và Branch · Collapsed Core/Distribution · Dual MPLS L2VPN · IPsec Routed</p></div>
        </div>
        <div className="topology-health-strip" aria-label="Trạng thái kiến trúc mạng">
          <span><i className="online" />Gateway VLAN 93 <strong>HQ · 10.10.93.1</strong></span>
          <span><i className={primaryDown ? "down" : "online"} />MPLS Primary <strong>{primaryDown ? "Degraded" : "Active"}</strong></span>
          <span><i className={backupDown ? "down" : "standby"} />MPLS Backup <strong>{backupDown ? "Down" : "Standby"}</strong></span>
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
            <div role="img" aria-label="Enterprise v7 Architecture" className="topology-vector-underlay" dangerouslySetInnerHTML={{ __html: topologyV7Svg }} />
            <svg viewBox="0 0 1900 880" className="topology-overlay-svg" aria-label="CCH Enterprise v7 topology canvas">
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
        <div className="topology-canvas-caption"><span><i className="hq" />HQ</span><b>VLAN 93 L2 extension</b><span>Branch<i className="branch" /></span></div>
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
            <div><Activity size={16} /><span><strong>Mininet runtime</strong> · Điều khiển tuyến MPLS Primary</span></div>
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

      <footer className="topology-v7-legend" aria-label="Chú thích sơ đồ mạng v7">
        <span><i className="legend-line vlan" /><strong>VLAN 93</strong> Gateway duy nhất tại HQ</span>
        <span><i className="legend-line mpls" /><strong>MPLS L2VPN</strong> Primary / Backup</span>
        <span><i className="legend-line ipsec" /><strong>IPsec L3</strong> Routed qua Firewall HA</span>
        <span><i className="legend-line partner" /><strong>Partner PBX/CRM</strong> Kết nối riêng</span>
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
