import { useEffect, useMemo, useRef, useState } from "react";
import {
  Download,
  Layers,
  Maximize2,
  Minimize2,
  Network,
  RotateCcw,
  Search,
  Sliders,
  ZoomIn,
  ZoomOut,
  Shield,
  Activity,
} from "lucide-react";
import type { Decision, Host, Link, Topology } from "../api/client";
import topologyV7Svg from "../assets/enterprise_logical_topology_v7.svg";
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

export const positions: Record<string, [number, number]> = {
  c0: [950, 50],
  project_1: [80, 710],
  project_2_hq: [195, 710],
  project_3: [310, 710],
  project_4: [425, 710],
  it_support: [545, 710],
  iot_hq: [545, 780],
  guest: [545, 840],
  access_floor1: [200, 590],
  access_floor2: [370, 590],
  infra_access: [685, 710],
  core_hq: [455, 430],
  hdhcp: [620, 850],
  hdns: [690, 850],
  had: [760, 850],
  hfile: [620, 915],
  hmonitor: [690, 915],
  hbackup: [760, 915],
  hntp: [830, 850],
  fw_hq: [450, 240],
  ce_hq1: [740, 425],
  ce_hq2: [740, 505],
  l2vpn_primary: [950, 425],
  l2vpn_backup: [950, 505],
  ipsec_l3: [950, 220],
  ce_branch1: [1160, 425],
  ce_branch2: [1160, 505],
  dist_branch: [1445, 430],
  access_branch: [1360, 590],
  project_2_branch: [1325, 710],
  iot_branch: [1595, 710],
  fw_telesale: [1445, 240],
  internet_zone: [950, 135],
  h90: [138, 250],
  hcall: [138, 200],
  hzalo: [1730, 145],
  hsocial: [1815, 145],
  hinternet: [1480, 140],
};

const nodeStyle: Record<string, { fill: string; stroke: string; color?: string }> = {
  user_group: { fill: "#ffffff", stroke: "#475467" },
  endpoint_group: { fill: "#ffffff", stroke: "#475467" },
  switch: { fill: "#f0f9ff", stroke: "#0284c7" },
  firewall: { fill: "#fef2f2", stroke: "#dc2626" },
  controller: { fill: "#f5f3ff", stroke: "#7c3aed" },
  ce_bridge: { fill: "#f0fdf4", stroke: "#16a34a" },
  l2vpn: { fill: "#fdf4ff", stroke: "#c026d3" },
  ipsec: { fill: "#fffbeb", stroke: "#d97706" },
  service_edge: { fill: "#f8fafc", stroke: "#64748b" },
  service: { fill: "#ffffff", stroke: "#64748b" },
  infrastructure_service: { fill: "#f0fdf4", stroke: "#059669" },
  partner: { fill: "#faf5ff", stroke: "#9333ea" },
  shared: { fill: "#f0fdf4", stroke: "#16a34a" },
};

export function canonicalProject2(id: string) {
  return id === "project_2_hq" || id === "project_2_branch" ? "project_2" : id;
}

export function displayNodes(topology?: Topology): DisplayNode[] {
  const groups = topology?.groups || [];
  return (topology?.nodes || []).flatMap((raw) => {
    const node = raw as DisplayNode;
    const group = groups.find((g) => g.id === String(node.id));
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

export function linkIsActive(path: string[], source: string, target: string) {
  const left = canonicalProject2(source);
  const right = canonicalProject2(target);
  return path.some((node, index) => {
    const next = path[index + 1];
    return (node === left && next === right) || (node === right && next === left);
  });
}

export function isBackupLink(link: Link) {
  return [link.source, link.target].some((id) => id.includes("hq2") || id.includes("branch2") || id.includes("backup"));
}

export function isPrimaryL2Link(link: Link) {
  return [link.source, link.target].some((id) => id.includes("hq1") || id.includes("branch1") || id.includes("l2vpn_primary"));
}

export function nodeType(node: DisplayNode) {
  const type = String(node.type || "");
  if (type) return type;
  if (node.id === "h90" || node.id === "hcall") return "partner";
  if (node.id === "project_2_hq" || node.id === "project_2_branch") return "shared";
  if (String(node.id).startsWith("h") && !String(node.id).startsWith("hq")) return "service";
  return "service";
}

export function nodeSubtitle(node: DisplayNode) {
  if (node.id === "core_hq") return "Collapsed Core/Distribution HA (HQ)";
  if (node.id === "dist_branch") return "Collapsed Core/Distribution HA (Branch)";
  if (node.id === "l2vpn_primary") return "VLAN 93 · ACTIVE (Primary)";
  if (node.id === "l2vpn_backup") return "VLAN 93 · STANDBY (Backup)";
  if (node.id === "ipsec_l3") return "Routed tunnel (FW-HQ ↔ FW-BR)";
  if (node.id === "fw_hq") return "Firewall HA Active (FW-HQ1/HQ2)";
  if (node.id === "fw_telesale") return "Firewall HA Active (FW-BR1/BR2)";
  if (node.id === "project_2_hq") return "VLAN 93 · Gateway 10.10.93.1";
  if (node.id === "project_2_branch") return "VLAN 93 · No Branch SVI";
  if (node.id === "h90") return "PBX / Contact Center";
  if (node.id === "hcall") return "Partner CRM";
  if (node.type === "user_group" || node.type === "endpoint_group") {
    const vlan = node.vlan == null ? "" : `VLAN ${String(node.vlan)}`;
    const count = node.count == null ? "" : `${String(node.count)} users`;
    return [count, vlan].filter(Boolean).join(" · ");
  }
  if (node.ip) return String(node.ip);
  return String(node.subtitle || "");
}

export function endpointForNode(node: DisplayNode) {
  return node.hosts?.[0]?.name || (String(node.id).startsWith("h") ? String(node.id) : undefined);
}

export default function TopologyCanvas({
  topology,
  links,
  flows = [],
  decision,
  activeIndex = 0,
  failedLinks,
  liveLinkControl,
  authenticated = false,
  linkOperation,
  source,
  destination,
  onFail,
  onRecover,
  onSource,
  onDestination,
}: Props) {
  const [viewMode, setViewMode] = useState<ViewMode>("interactive");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [selectedNode, setSelectedNode] = useState<DisplayNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<DisplayNode | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [fullscreen, setFullscreen] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const nodes = useMemo(() => displayNodes(topology), [topology]);
  const visibleLinks = useMemo(() => displayLinks(links), [links]);
  const path = decision?.path || [];
  const l2Controls = useMemo(() => visibleLinks.filter(isPrimaryL2Link), [visibleLinks]);

  // Sync default endpoints if available
  useEffect(() => {
    if (!topology?.hosts?.length) return;
    const names = new Set(topology.hosts.map((host) => host.name));
    if (!names.has(source)) {
      const fallback = topology.hosts.find((host) => host.name === "h101_01")?.name
        || topology.hosts.find((host) => host.kind === "user")?.name;
      if (fallback) onSource(fallback);
    }
    if (!names.has(destination)) {
      const fallback = topology.hosts.find((host) => host.name === "h90")?.name
        || topology.hosts.find((host) => host.kind === "service")?.name;
      if (fallback) onDestination(fallback);
    }
  }, [destination, onDestination, onSource, source, topology]);

  const handleZoom = (delta: number) => {
    setZoom((prev) => Math.min(Math.max(0.5, Number((prev + delta).toFixed(2))), 3.0));
  };

  const handleResetZoom = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleWheel = (e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey || viewMode === "architecture") {
      e.preventDefault();
      const delta = e.deltaY < 0 ? 0.1 : -0.1;
      handleZoom(delta);
    }
  };

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      void containerRef.current.requestFullscreen().then(() => setFullscreen(true)).catch(() => {});
    } else {
      void document.exitFullscreen().then(() => setFullscreen(false)).catch(() => {});
    }
  };

  const filteredNodeIds = useMemo(() => {
    if (!searchQuery.trim()) return null;
    const q = searchQuery.toLowerCase();
    return new Set(
      nodes
        .filter((n) => String(n.id).toLowerCase().includes(q) || String(n.label || "").toLowerCase().includes(q) || String(n.subnet || "").toLowerCase().includes(q) || String(n.vlan || "").includes(q))
        .map((n) => n.id)
    );
  }, [nodes, searchQuery]);

  const currentNodeInPath = path[activeIndex];
  const blockedNodeId = decision?.blocked_at;

  const nodeFlows = useMemo(() => {
    if (!selectedNode) return [];
    return flows.filter((flow) => flow.switch === selectedNode.id || flow.node === selectedNode.id);
  }, [flows, selectedNode]);

  return (
    <section
      ref={containerRef}
      className={`topology-page ${fullscreen ? "fullscreen-mode" : ""}`}
      data-testid="topology-canvas"
    >
      {/* Header Toolbar */}
      <div className="topology-toolbar-header">
        <div className="topology-title-area">
          <div className="topology-title-row">
            <Network className="topology-header-icon" size={22} />
            <div>
              <h2>Sơ đồ logic mạng doanh nghiệp · v7</h2>
              <p>
                Trụ sở chính + Chi nhánh | 2-tier Collapsed Core/Distribution | VLAN 93 MPLS L2VPN | IPsec Routed Intersite
              </p>
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="topology-controls-bar">
          {/* Mode Switcher */}
          <div className="segmented topology-mode-selector" role="tablist" aria-label="Chế độ xem topology">
            <button
              type="button"
              role="tab"
              aria-selected={viewMode === "interactive"}
              className={viewMode === "interactive" ? "active" : ""}
              onClick={() => setViewMode("interactive")}
              title="Mô phỏng tương tác động"
            >
              <Activity size={14} />
              <span>Mô phỏng tương tác</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={viewMode === "architecture"}
              className={viewMode === "architecture" ? "active" : ""}
              onClick={() => setViewMode("architecture")}
              title="Sơ đồ kiến trúc vector chuẩn v7"
            >
              <Layers size={14} />
              <span>Sơ đồ chuẩn v7</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={viewMode === "integrated"}
              className={viewMode === "integrated" ? "active" : ""}
              onClick={() => setViewMode("integrated")}
              title="Chế độ kết hợp mô phỏng & kiến trúc"
            >
              <Sliders size={14} />
              <span>Chế độ kết hợp</span>
            </button>
          </div>

          {/* Search Filter */}
          <div className="topology-search-box">
            <Search size={14} />
            <input
              type="text"
              placeholder="Tìm node / VLAN / IP..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="Tìm kiếm thiết bị"
            />
            {searchQuery && (
              <button type="button" className="clear-search" onClick={() => setSearchQuery("")}>
                ×
              </button>
            )}
          </div>

          {/* Zoom / Navigation Tools */}
          <div className="topology-zoom-tools">
            <button type="button" className="icon-button" onClick={() => handleZoom(0.15)} title="Phóng to (Zoom In)" aria-label="Phóng to">
              <ZoomIn size={16} />
            </button>
            <span className="zoom-level-indicator">{Math.round(zoom * 100)}%</span>
            <button type="button" className="icon-button" onClick={() => handleZoom(-0.15)} title="Thu nhỏ (Zoom Out)" aria-label="Thu nhỏ">
              <ZoomOut size={16} />
            </button>
            <button type="button" className="icon-button" onClick={handleResetZoom} title="Khôi phục kích thước ban đầu" aria-label="Reset Zoom">
              <RotateCcw size={16} />
            </button>
            <button type="button" className="icon-button" onClick={toggleFullscreen} title="Toàn màn hình" aria-label="Fullscreen">
              {fullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            </button>
            <a
              href={topologyV7Svg}
              download="enterprise_logical_topology_v7.svg"
              className="icon-button download-asset-btn"
              title="Tải sơ đồ vector SVG gốc"
              aria-label="Download SVG"
            >
              <Download size={16} />
            </a>
          </div>
        </div>
      </div>

      {/* Simulation Honesty Banner */}
      <div className="topology-simulation-banner">
        <div className="banner-badge">
          <Shield size={14} />
          <strong>Simulation Honesty (v7)</strong>
        </div>
        <span className="banner-text">
          Core/Dist = HA pair abstraction · Firewall = 1 active namespace/pair · MPLS = L2 transparent bridge · IPsec = routed tunnel.
        </span>
      </div>

      {/* Canvas View Area */}
      <div
        className={`topology-svg-viewport ${isDragging ? "dragging" : ""}`}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        tabIndex={0}
        aria-label="Vùng hiển thị sơ đồ mạng"
      >
        <div
          className="topology-canvas-stage"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            transformOrigin: "center center",
            transition: isDragging ? "none" : "transform 0.15s ease-out",
          }}
        >
          {/* Official Vector Architecture Mode */}
          {viewMode === "architecture" && (
            <div className="topology-architecture-view">
              <img
                src={topologyV7Svg}
                alt="Sơ đồ logic mạng doanh nghiệp v7"
                className="topology-v7-image"
                draggable={false}
              />
            </div>
          )}

          {/* Interactive Simulation or Integrated Mode */}
          {(viewMode === "interactive" || viewMode === "integrated") && (
            <div className="topology-interactive-view">
              {viewMode === "integrated" && (
                <img
                  src={topologyV7Svg}
                  alt="Enterprise v7 Background"
                  className="topology-integrated-backdrop"
                  draggable={false}
                />
              )}

              <svg
                viewBox="0 0 1900 1000"
                className="topology-main-svg"
                role="img"
                aria-label="CCH Enterprise v7 topology canvas"
              >
                {/* Zone Boundaries for Interactive Mode */}
                {viewMode === "interactive" && (
                  <>
                    {/* HQ Zone */}
                    <rect x="30" y="80" width="790" height="880" rx="14" fill="#f8fafc" stroke="#94a3b8" strokeDasharray="8 6" strokeWidth="1.6" />
                    <text x="55" y="115" fontSize="20" fontWeight="800" fill="#1e293b">TRỤ SỞ CHÍNH (HQ)</text>
                    <text x="55" y="135" fontSize="11" fill="#64748b">2-tier Collapsed Core / Distribution · SVI Gateway tại HQ</text>

                    {/* Branch Zone */}
                    <rect x="1080" y="80" width="790" height="880" rx="14" fill="#f8fafc" stroke="#94a3b8" strokeDasharray="8 6" strokeWidth="1.6" />
                    <text x="1840" y="115" fontSize="20" fontWeight="800" fill="#1e293b" textAnchor="end">CHI NHÁNH (BRANCH)</text>
                    <text x="1840" y="135" fontSize="11" fill="#64748b" textAnchor="end">Không có SVI Gateway VLAN 93 · L2 Extension qua WAN</text>

                    {/* WAN Services Zone */}
                    <rect x="835" y="190" width="230" height="380" rx="16" fill="#fffbeb" stroke="#f59e0b" strokeDasharray="6 6" strokeWidth="1.8" />
                    <text x="950" y="215" fontSize="13" fontWeight="800" fill="#b45309" textAnchor="middle">WAN SERVICES</text>
                    <text x="950" y="230" fontSize="9.5" fill="#92400e" textAnchor="middle">MPLS L2VPN & IPsec Tunnel</text>
                  </>
                )}

                {/* Render Links */}
                {visibleLinks.map((link) => {
                  const from = positions[link.source];
                  const to = positions[link.target];
                  if (!from || !to) return null;

                  const backup = isBackupLink(link);
                  const standby = link.status === "standby" || (backup && link.status === "down" && !failedLinks.includes(link.id));
                  const down = failedLinks.includes(link.id) || (link.status === "down" && !standby);
                  const active = linkIsActive(path, link.source, link.target);

                  const x1 = from[0] + 65;
                  const y1 = from[1] + 25;
                  const x2 = to[0] + 65;
                  const y2 = to[1] + 25;

                  return (
                    <g key={link.id} className="topology-link-group">
                      {/* Wider transparent stroke for easier clicking/hover */}
                      <line
                        x1={x1}
                        y1={y1}
                        x2={x2}
                        y2={y2}
                        stroke="transparent"
                        strokeWidth={14}
                        role="button"
                        aria-label={`Link ${link.source} đến ${link.target}`}
                        tabIndex={0}
                      />
                      <line
                        x1={x1}
                        y1={y1}
                        x2={x2}
                        y2={y2}
                        stroke={down ? "#ef4444" : active ? "#2563eb" : standby ? "#a855f7" : "#94a3b8"}
                        strokeWidth={active ? 4.5 : standby || down ? 2.5 : 2}
                        strokeDasharray={standby || down ? "8 6" : active ? undefined : undefined}
                        opacity={down ? 0.6 : standby ? 0.75 : 0.9}
                        className={active ? "link-pulse" : ""}
                      />
                      {active && (
                        <circle r={5} fill="#2563eb">
                          <animateMotion
                            path={`M ${x1} ${y1} L ${x2} ${y2}`}
                            dur="1.2s"
                            repeatCount="indefinite"
                          />
                        </circle>
                      )}
                    </g>
                  );
                })}

                {/* Blocked At Marker */}
                {blockedNodeId && positions[blockedNodeId] && (
                  <g
                    data-testid="blocked-at"
                    className="deny-mark-animated"
                    transform={`translate(${positions[blockedNodeId][0] + 65}, ${positions[blockedNodeId][1] + 25})`}
                  >
                    <circle r={22} fill="rgba(239, 68, 68, 0.2)" stroke="#ef4444" strokeWidth={2} />
                    <line x1="-10" y1="-10" x2="10" y2="10" stroke="#ef4444" strokeWidth={3.5} strokeLinecap="round" />
                    <line x1="10" y1="-10" x2="-10" y2="10" stroke="#ef4444" strokeWidth={3.5} strokeLinecap="round" />
                  </g>
                )}

                {/* Render Nodes */}
                {nodes.map((node) => {
                  const position = positions[node.id];
                  if (!position) return null;

                  const style = nodeStyle[nodeType(node)] || nodeStyle.service;
                  const endpoint = endpointForNode(node);
                  const isSource = source === endpoint;
                  const isDestination = destination === endpoint;
                  const selected = isSource || isDestination;
                  const isCurrentInPath = currentNodeInPath && (node.id === currentNodeInPath || canonicalProject2(node.id) === currentNodeInPath);
                  const isBlocked = blockedNodeId === node.id || canonicalProject2(node.id) === blockedNodeId;
                  const isDimmed = filteredNodeIds ? !filteredNodeIds.has(node.id) : false;

                  const width = 130;
                  const height = 52;

                  return (
                    <g
                      key={node.id}
                      transform={`translate(${position[0]}, ${position[1]})`}
                      className={`topology-node-group ${isDimmed ? "dimmed" : ""} ${isCurrentInPath ? "current" : ""}`}
                      role="button"
                      aria-label={`Node ${String(node.label || node.id)}`}
                      tabIndex={0}
                      onClick={() => {
                        setSelectedNode(node);
                        if (endpoint) {
                          if (source === endpoint) onDestination(endpoint);
                          else onSource(endpoint);
                        }
                      }}
                      onMouseEnter={() => setHoveredNode(node)}
                      onMouseLeave={() => setHoveredNode(null)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          setSelectedNode(node);
                          if (endpoint) onSource(endpoint);
                        }
                      }}
                    >
                      {/* Node Box */}
                      <rect
                        width={width}
                        height={height}
                        rx={8}
                        fill={isBlocked ? "#fef2f2" : isCurrentInPath ? "#eff6ff" : selected ? "#f8fafc" : style.fill}
                        stroke={
                          isBlocked
                            ? "#ef4444"
                            : isCurrentInPath
                            ? "#2563eb"
                            : selected
                            ? "#0f172a"
                            : style.stroke
                        }
                        strokeWidth={isCurrentInPath || selected ? 2.8 : 1.6}
                        className="node-rect-shadow"
                      />

                      {/* Source/Destination Indicator Badges */}
                      {isSource && (
                        <g transform="translate(4, -8)">
                          <rect width={48} height={16} rx={4} fill="#2563eb" />
                          <text x={24} y={11} fill="#ffffff" fontSize="9" fontWeight="800" textAnchor="middle">
                            NGUỒN
                          </text>
                        </g>
                      )}
                      {isDestination && (
                        <g transform="translate(78, -8)">
                          <rect width={48} height={16} rx={4} fill="#059669" />
                          <text x={24} y={11} fill="#ffffff" fontSize="9" fontWeight="800" textAnchor="middle">
                            ĐÍCH
                          </text>
                        </g>
                      )}

                      {/* Node Title */}
                      <text
                        x={width / 2}
                        y={20}
                        textAnchor="middle"
                        fontSize="11.5"
                        fontWeight="700"
                        fill="#0f172a"
                      >
                        {String(node.label || node.id).slice(0, 22)}
                      </text>

                      {/* Node Subtitle */}
                      <text
                        x={width / 2}
                        y={36}
                        textAnchor="middle"
                        fontSize="8.5"
                        fontWeight="500"
                        fill="#64748b"
                      >
                        {nodeSubtitle(node).slice(0, 30)}
                      </text>
                    </g>
                  );
                })}
              </svg>
            </div>
          )}
        </div>
      </div>

      {/* Floating Tooltip when hovering over a node */}
      {hoveredNode && positions[hoveredNode.id] && (
        <div className="topology-hover-tooltip" role="tooltip">
          <div className="tooltip-title">{String(hoveredNode.label || hoveredNode.id)}</div>
          <div className="tooltip-meta">
            <span><strong>Vai trò:</strong> {String(hoveredNode.type || "device")}</span>
            {hoveredNode.vlan != null && <span><strong>VLAN:</strong> {String(hoveredNode.vlan)}</span>}
            {hoveredNode.subnet && <span><strong>Subnet:</strong> {hoveredNode.subnet}</span>}
            {hoveredNode.ip && <span><strong>IP:</strong> {hoveredNode.ip}</span>}
            {hoveredNode.count != null && <span><strong>Endpoints:</strong> {hoveredNode.count} hosts</span>}
          </div>
          <div className="tooltip-hint">Click để chọn làm nguồn/đích hoặc xem chi tiết</div>
        </div>
      )}

      {/* Enterprise v7 Legend */}
      <div className="topology-v7-legend" aria-label="Chú thích sơ đồ mạng v7">
        <div className="legend-item">
          <span className="legend-tag vlan93">VLAN 93</span>
          <span>Gateway <code>10.10.93.1</code> tại HQ; Chi nhánh không có SVI (Layer-2 Extension).</span>
        </div>
        <div className="legend-item">
          <span className="legend-tag mpls">MPLS L2VPN</span>
          <span>CE1 / Primary (Active), CE2 / Backup (Standby) ngăn loop L2 trên đường trục WAN.</span>
        </div>
        <div className="legend-item">
          <span className="legend-tag ipsec">IPsec L3</span>
          <span>Mô phỏng routed tunnel Firewall HQ ↔ Firewall Branch cho toàn bộ luồng routed.</span>
        </div>
        <div className="legend-item">
          <span className="legend-tag partner">Partner PBX/CRM</span>
          <span>Hệ thống đối tác đặt tại vùng kết nối riêng, độc lập với Server Farm nội bộ.</span>
        </div>
      </div>

      {/* L2VPN Primary Path Controls */}
      <div className="topology-link-controls-section">
        <div className="controls-header">
          <Sliders size={15} />
          <strong>Điều khiển L2VPN Primary Path (Live Mininet Control):</strong>
        </div>
        <div className="topology-link-controls" aria-label="L2VPN primary path controls">
          {l2Controls.map((link) => {
            const down = failedLinks.includes(link.id) || link.status === "down";
            const busy = linkOperation?.linkId === link.id && linkOperation.status === "running";
            return (
              <button
                type="button"
                key={link.id}
                className={down ? "recover-btn" : "fail-btn"}
                disabled={!authenticated || !liveLinkControl || busy}
                onClick={() => (down ? onRecover(link.id) : onFail(link.id))}
                title={`Điều khiển liên kết ${link.source} ↔ ${link.target}`}
              >
                {down ? "Khôi phục Primary" : "Ngắt thử nghiệm Primary"} · {link.source} ↔ {link.target}
              </button>
            );
          })}
        </div>
      </div>

      {/* Node Inspector Drawer */}
      <Drawer
        open={Boolean(selectedNode)}
        title={selectedNode ? `Chi tiết Node · ${selectedNode.label || selectedNode.id}` : "Inspector"}
        onClose={() => setSelectedNode(null)}
      >
        {selectedNode && (
          <div className="inspector-grid">
            <StatusBadge
              status={currentNodeInPath === selectedNode.id ? "online" : "unknown"}
              label={currentNodeInPath === selectedNode.id ? "Đang có luồng dữ liệu" : "Đang hoạt động"}
            />
            <dl>
              <dt>Tên thiết bị / Group</dt>
              <dd>{String(selectedNode.id)}</dd>
              <dt>Nhãn hiển thị</dt>
              <dd>{String(selectedNode.label || selectedNode.id)}</dd>
              <dt>Phân loại</dt>
              <dd>{String(selectedNode.type || "device")}</dd>
              <dt>Mô tả vai trò</dt>
              <dd>{nodeSubtitle(selectedNode)}</dd>
              <dt>Site</dt>
              <dd>{String(selectedNode.site || "HQ").toUpperCase()}</dd>
              {selectedNode.vlan != null && (
                <>
                  <dt>VLAN</dt>
                  <dd>VLAN {String(selectedNode.vlan)}</dd>
                </>
              )}
              {selectedNode.subnet && (
                <>
                  <dt>Subnet</dt>
                  <dd>{selectedNode.subnet}</dd>
                </>
              )}
              {selectedNode.ip && (
                <>
                  <dt>IP Address</dt>
                  <dd>{selectedNode.ip}</dd>
                </>
              )}
              <dt>Số lượng Flow</dt>
              <dd>{nodeFlows.length} flows</dd>
            </dl>

            {/* Host list if it's a group */}
            {selectedNode.hosts && selectedNode.hosts.length > 0 && (
              <div className="inspector-hosts">
                <strong>Danh sách Endpoints ({selectedNode.hosts.length})</strong>
                <div className="host-chips-grid">
                  {selectedNode.hosts.map((host) => (
                    <button
                      key={host.name}
                      type="button"
                      className={`host-chip ${source === host.name ? "is-source" : destination === host.name ? "is-dest" : ""}`}
                      onClick={() => {
                        if (source === host.name) onDestination(host.name);
                        else onSource(host.name);
                      }}
                    >
                      <span>{host.name}</span>
                      <small>{host.ip}</small>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Quick Actions */}
            {endpointForNode(selectedNode) && (
              <div className="drawer-actions">
                <button
                  type="button"
                  className="primary"
                  onClick={() => {
                    const ep = endpointForNode(selectedNode);
                    if (ep) onSource(ep);
                  }}
                >
                  Chọn làm Nguồn (Source)
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const ep = endpointForNode(selectedNode);
                    if (ep) onDestination(ep);
                  }}
                >
                  Chọn làm Đích (Destination)
                </button>
              </div>
            )}
          </div>
        )}
      </Drawer>
    </section>
  );
}
