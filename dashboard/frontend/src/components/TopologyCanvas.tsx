import { Focus, Layers3, Maximize2, RotateCcw, Search, Unplug, ZoomIn, ZoomOut } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import type { Decision, Host, Link, Topology } from "../api/client";
import ConfirmDialog from "./ui/ConfirmDialog";
import Drawer from "./ui/Drawer";
import StatusBadge from "./ui/StatusBadge";

const positions: Record<string, [number, number]> = {
  project_a: [90, 145], project_b: [90, 225], project_c: [90, 305], it_support: [90, 385], h90: [90, 465],
  access_hq_a: [270, 145], access_hq_b: [270, 225], access_hq_c: [270, 305], access_hq_it: [270, 385], voice_access: [270, 465],
  core_hq: [470, 305], fw_hq: [665, 305], ce_hq: [790, 305],
  c0: [775, 70], mpls_cloud: [900, 455],
  telesale: [90, 635], backoffice: [90, 735], access_branch: [270, 685], dist_branch: [470, 685],
  fw_branch: [665, 745], ce_branch: [790, 650],
  internet: [1085, 620],
  hzalo: [1260, 165], hcall: [1260, 315], hsocial: [1260, 555], hinternet: [1260, 725],
};

const routedLinks: Record<string, [number, number][]> = {
  "core_hq-fw_hq": [[470, 305], [665, 305]],
  "fw_hq-internet": [[665, 305], [1040, 305], [1040, 620], [1085, 620]],
  "dist_branch-fw_branch": [[470, 685], [565, 685], [565, 745], [665, 745]],
  "fw_branch-internet": [[665, 745], [900, 745], [900, 620], [1085, 620]],
};

const regions: Record<string, string> = {
  project_a: "hq", project_b: "hq", project_c: "hq", it_support: "hq", h90: "hq",
  access_hq_a: "hq", access_hq_b: "hq", access_hq_c: "hq", access_hq_it: "hq", voice_access: "hq",
  core_hq: "hq", fw_hq: "hq", ce_hq: "hq", c0: "control",
  mpls_cloud: "wan",
  telesale: "branch", backoffice: "branch", access_branch: "branch", dist_branch: "branch", fw_branch: "branch", ce_branch: "branch",
  internet: "services", hzalo: "services", hcall: "services", hsocial: "services", hinternet: "services",
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
    else if (node.type === "user_group") subtitle = `${node.count} users · VLAN ${node.vlan}`;
    else if (node.type === "switch") subtitle = "Open vSwitch";
    else if (node.type === "firewall") subtitle = "Internet Edge Boundary";
    else if (node.type === "wan") subtitle = "WAN transport";
    else if (node.type === "controller") subtitle = "127.0.0.1:6653";
    else if (node.ip) subtitle = String(node.ip);
    labels[id] = [title, subtitle];
  });
  return labels;
}

function nodeClass(type: string, id: string) {
  if (type === "user_group") return "user";
  if (type === "switch") return "switch";
  if (type === "router") return "router";
  if (type === "wan") return "cloud";
  if (type === "firewall") return "firewall";
  if (type === "controller") return "controller";
  if (id === "hsocial") return "blocked";
  return "service";
}

export default function TopologyCanvas(props: Props) {
  const sectionRef = useRef<HTMLElement>(null);
  const labels = useMemo(() => labelMap(props.topology), [props.topology]);
  const [zoom, setZoom] = useState(1);
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState("all");
  const [mode, setMode] = useState<"simple" | "technical">("simple");
  const [legendVisible, setLegendVisible] = useState(true);
  const [inspector, setInspector] = useState<Inspector>(null);
  const [confirmLink, setConfirmLink] = useState<{ id: string; action: "fail" | "recover" } | null>(null);

  const currentNode = props.decision?.path[Math.min(props.activeIndex, Math.max(0, props.decision.path.length - 1))];
  const controlledNodes = useMemo(
    () => (props.topology?.nodes || []).filter((node) => node.type === "switch" && positions[String(node.id)]),
    [props.topology],
  );
  const selectedNode = inspector?.kind === "node"
    ? props.topology?.nodes.find((node) => String(node.id) === inspector.id)
    : undefined;
  const selectedLink = inspector?.kind === "link"
    ? props.links.find((link) => link.id === inspector.id)
    : undefined;
  const selectedGroup = selectedNode
    ? props.topology?.groups.find((group) => group.id === String(selectedNode.id))
    : undefined;
  const matchingNodes = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return new Set<string>();
    return new Set((props.topology?.nodes || [])
      .filter((node) => JSON.stringify(node).toLowerCase().includes(needle))
      .map((node) => String(node.id)));
  }, [props.topology, query]);

  const nodeVisible = (id: string) => region === "all" || regions[id] === region || (region === "hq" && id === "c0");
  const flowForNode = selectedNode
    ? (props.flows || []).filter((flow) => String(flow.switch || "") === String(selectedNode.id))
    : [];
  const nodeTraffic = flowForNode.reduce((sum, flow) => sum + Number(flow.bytes || 0), 0);
  const relatedLinks = selectedNode
    ? props.links.filter((link) => link.source === selectedNode.id || link.target === selectedNode.id)
    : [];
  const linkStatus = selectedLink
    ? (props.failedLinks.includes(selectedLink.id) || selectedLink.status === "down" ? "offline" : selectedLink.status === "degraded" ? "degraded" : "online")
    : "unknown";
  const selectedLinkOperation = selectedLink && props.linkOperation?.linkId === selectedLink.id ? props.linkOperation : undefined;

  const chooseEndpoint = (kind: "source" | "destination") => {
    if (!selectedNode) return;
    const endpoint = selectedGroup?.hosts[0]?.name || String(selectedNode.id);
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
            <option value="branch">Branch</option><option value="services">Internet/Services</option>
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
        <svg className="topology-svg" style={{ width: `${zoom * 100}%` }} viewBox="0 0 1360 820" aria-label="Sơ đồ mạng Hybrid MPLS và SDN">
          <rect className="zone" x="20" y="95" width="780" height="430" /><text className="zone-label" x="35" y="117">HQ</text>
          <rect className="zone" x="20" y="575" width="780" height="220" /><text className="zone-label" x="35" y="597">BRANCH</text>
          <rect className="zone" x="815" y="185" width="220" height="610" /><text className="zone-label" x="830" y="207">MPLS L3VPN LOGIC</text>
          <rect className="zone" x="1045" y="95" width="295" height="700" /><text className="zone-label" x="1060" y="117">INTERNET / SERVICES</text>

          {mode === "technical" && controlledNodes.map((node) => {
            const target = positions[String(node.id)];
            const controller = positions.c0;
            return <line data-testid="control-path" key={`control-${String(node.id)}`} x1={controller[0]} y1={controller[1] + 25} x2={target[0]} y2={target[1]} className="topology-link control" />;
          })}

          {props.links.filter((link) => link.type !== "control").map((link) => {
            const from = positions[link.source];
            const to = positions[link.target];
            if (!from || !to) return null;
            const active = props.decision ? isPathLink(props.decision.path, link.source, link.target) : false;
            const failed = link.status === "down" || props.failedLinks.includes(link.id);
            const route = routedLinks[link.id];
            const visible = nodeVisible(link.source) && nodeVisible(link.target);
            const className = `topology-link data-link ${link.type} ${active ? props.decision?.action : ""} ${failed ? "failed" : ""} ${visible ? "" : "region-hidden"}`;
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
            const node = props.topology?.nodes.find((item) => String(item.id) === id);
            const type = String(node?.type || "");
            const matched = matchingNodes.has(id);
            const dimmed = query && !matched;
            return (
              <g
                className={`topology-node ${nodeClass(type, id)} ${currentNode === id ? "current" : ""} ${dimmed ? "search-dimmed" : ""} ${nodeVisible(id) ? "" : "region-hidden"}`}
                key={id}
                transform={`translate(${x - 60} ${y - 25})`}
                onClick={() => setInspector({ kind: "node", id })}
                role="button"
                aria-label={`Node ${title}`}
              >
                <rect width="120" height="50" rx="5" />
                <text x="60" y="20">{title}</text>
                <text className="node-subtitle" x="60" y="36">{subtitle}</text>
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
          <span><i className="mpls" />MPLS transport</span>
        </div>
      )}
      <Drawer open={Boolean(inspector)} title={selectedNode ? `Node · ${String(selectedNode.label || selectedNode.id)}` : selectedLink ? `Link · ${selectedLink.source} → ${selectedLink.target}` : "Inspector"} onClose={() => setInspector(null)}>
        {selectedNode && (
          <div className="inspector-grid">
            <StatusBadge status={currentNode === selectedNode.id ? "online" : "unknown"} label={currentNode === selectedNode.id ? "Đang có packet" : "Theo inventory"} />
            <dl>
              <dt>Tên</dt><dd>{String(selectedNode.id)}</dd>
              <dt>Vai trò</dt><dd>{String(selectedNode.type || "unknown")}</dd>
              <dt>IP/Subnet</dt><dd>{String(selectedNode.ip || selectedNode.subnet || "N/A")}</dd>
              <dt>VLAN/Group</dt><dd>{String(selectedNode.vlan || selectedNode.group || "N/A")}</dd>
              <dt>Managed by controller</dt><dd>{selectedNode.type === "switch" ? "Có" : "Không"}</dd>
              <dt>DPID</dt><dd>{String(selectedNode.dpid || "N/A")}</dd>
              <dt>Flow count</dt><dd>{flowForNode.length}</dd>
              <dt>Traffic</dt><dd>{nodeTraffic.toLocaleString("vi-VN")} bytes</dd>
              <dt>Link liên quan</dt><dd>{relatedLinks.length}</dd>
            </dl>
            {selectedGroup && (
              <div className="inspector-hosts">
                <strong>{selectedGroup.label} · {selectedGroup.subnet}</strong>
                {selectedGroup.hosts.slice(0, 10).map((host: Host) => <span key={host.name}>{host.name} · {host.ip}</span>)}
              </div>
            )}
            {["user_group", "service", "blocked_service"].includes(String(selectedNode.type)) && (
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
              <dt>Bandwidth</dt><dd>{String(selectedLink.bandwidth_mbps || "N/A")} Mbps</dd>
              <dt>Delay</dt><dd>{String(selectedLink.delay_ms || "N/A")} ms</dd>
              <dt>Loss</dt><dd>{String(selectedLink.loss_percent || "N/A")}%</dd>
            </dl>
            {props.liveLinkControl && selectedLink.type !== "control" && (
              <div className="drawer-actions">
                <button className="danger" disabled={!props.authenticated || selectedLinkOperation?.status === "running"} onClick={() => setConfirmLink({ id: selectedLink.id, action: "fail" })}><Unplug size={15} />Fail link</button>
                <button disabled={!props.authenticated || selectedLinkOperation?.status === "running"} onClick={() => setConfirmLink({ id: selectedLink.id, action: "recover" })}><RotateCcw size={15} />Recover</button>
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
