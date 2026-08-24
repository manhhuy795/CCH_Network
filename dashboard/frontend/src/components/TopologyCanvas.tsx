import { useEffect, useMemo } from "react";
import type { Decision, Host, Link, Topology } from "../api/client";


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

type DisplayNode = Record<string, unknown> & {
  id: string;
  label?: string;
  type?: string;
  site?: string;
  hosts?: Host[];
};

const positions: Record<string, [number, number]> = {
  c0: [900, 55],
  project_1: [80, 150],
  project_2_hq: [80, 235],
  project_3: [80, 320],
  project_4: [80, 405],
  it_support: [80, 490],
  iot_hq: [80, 575],
  guest: [80, 660],
  access_floor1: [300, 235],
  access_floor2: [300, 405],
  infra_access: [300, 690],
  core_hq: [560, 380],
  hdhcp: [530, 715],
  hdns: [650, 715],
  had: [770, 715],
  hfile: [890, 715],
  hmonitor: [1010, 715],
  hbackup: [1130, 715],
  hntp: [1250, 715],
  fw_hq: [760, 190],
  ce_hq1: [760, 390],
  ce_hq2: [760, 500],
  l2vpn_primary: [970, 390],
  l2vpn_backup: [970, 500],
  ipsec_l3: [970, 625],
  ce_branch1: [1180, 390],
  ce_branch2: [1180, 500],
  dist_branch: [1400, 480],
  access_branch: [1580, 480],
  project_2_branch: [1760, 420],
  iot_branch: [1760, 540],
  fw_telesale: [1400, 690],
  internet_zone: [1050, 190],
  h90: [1310, 95],
  hcall: [1450, 95],
  hzalo: [1310, 190],
  hsocial: [1450, 190],
  hinternet: [1380, 285],
};

const nodeStyle: Record<string, { fill: string; stroke: string }> = {
  user_group: { fill: "#ffffff", stroke: "#475467" },
  endpoint_group: { fill: "#ffffff", stroke: "#475467" },
  switch: { fill: "#eef4ff", stroke: "#155eef" },
  firewall: { fill: "#fff4ed", stroke: "#e62e05" },
  controller: { fill: "#f4f3ff", stroke: "#6938ef" },
  ce_bridge: { fill: "#ecfdf3", stroke: "#039855" },
  l2vpn: { fill: "#fdf2fa", stroke: "#c11574" },
  ipsec: { fill: "#fffaeb", stroke: "#dc6803" },
  service_edge: { fill: "#f2f4f7", stroke: "#667085" },
  service: { fill: "#f9fafb", stroke: "#98a2b3" },
  infrastructure_service: { fill: "#f0f9ff", stroke: "#026aa2" },
};

function canonicalProject2(id: string) {
  return id === "project_2_hq" || id === "project_2_branch" ? "project_2" : id;
}

function displayNodes(topology?: Topology): DisplayNode[] {
  const groups = topology?.groups || [];
  return (topology?.nodes || []).flatMap((raw) => {
    const node = raw as DisplayNode;
    if (String(node.id) !== "project_2") return [{ ...node, id: String(node.id) }];
    const hosts = groups.find((group) => group.id === "project_2")?.hosts || [];
    const hq = hosts.filter((host) => host.site === "hq");
    const branch = hosts.filter((host) => host.site === "branch" || host.site === "telesale");
    return [
      { ...node, id: "project_2_hq", label: "Dự án 2 · HQ · VLAN 93", site: "hq", hosts: hq, count: hq.length },
      { ...node, id: "project_2_branch", label: "Dự án 2 · Branch · VLAN 93", site: "branch", hosts: branch, count: branch.length },
    ];
  });
}

function displayLinks(links: Link[]): Link[] {
  return links.map((link) => {
    let source = link.source;
    let target = link.target;
    if (source === "project_2") source = target === "access_branch" ? "project_2_branch" : "project_2_hq";
    if (target === "project_2") target = source === "access_branch" ? "project_2_branch" : "project_2_hq";
    return { ...link, source, target };
  });
}

function linkIsActive(path: string[], source: string, target: string) {
  const left = canonicalProject2(source);
  const right = canonicalProject2(target);
  return path.some((node, index) => {
    const next = path[index + 1];
    return (node === left && next === right) || (node === right && next === left);
  });
}

function isBackupLink(link: Link) {
  return [link.source, link.target].some((id) => id.includes("hq2") || id.includes("branch2") || id.includes("backup"));
}

function isPrimaryL2Link(link: Link) {
  return [link.source, link.target].some((id) => id.includes("hq1") || id.includes("branch1") || id.includes("l2vpn_primary"));
}

function nodeType(node: DisplayNode) {
  const type = String(node.type || "");
  if (type) return type;
  if (String(node.id).startsWith("h") && !String(node.id).startsWith("hq")) return "service";
  return "service";
}

function nodeSubtitle(node: DisplayNode) {
  if (node.id === "core_hq") return "Collapsed Core/Distribution HA abstraction";
  if (node.id === "dist_branch") return "Collapsed Core/Distribution HA abstraction";
  if (node.id === "l2vpn_primary") return "VLAN 93 · ACTIVE";
  if (node.id === "l2vpn_backup") return "VLAN 93 · STANDBY";
  if (node.id === "ipsec_l3") return "Routed tunnel abstraction · no IKE/ESP proof";
  if (node.id === "fw_hq" || node.id === "fw_telesale") return "Firewall HA active-cluster abstraction";
  if (node.id === "project_2_hq") return "10 runtime users · GW 10.10.93.1 at HQ";
  if (node.id === "project_2_branch") return "10 runtime users · no Branch SVI";
  if (node.id === "h90") return "Partner PBX / Contact Center";
  if (node.id === "hcall") return "Partner CRM";
  if (node.type === "user_group" || node.type === "endpoint_group") {
    const vlan = node.vlan == null ? "" : ` · VLAN ${String(node.vlan)}`;
    const count = node.count == null ? "" : `${String(node.count)} endpoints`;
    return `${count}${vlan}`;
  }
  if (node.ip) return String(node.ip);
  return String(node.subtitle || "");
}

function endpointForNode(node: DisplayNode) {
  const first = node.hosts?.[0];
  return first?.name;
}

export default function TopologyCanvas({
  topology,
  links,
  decision,
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
  const nodes = useMemo(() => displayNodes(topology), [topology]);
  const visibleLinks = useMemo(() => displayLinks(links), [links]);
  const path = decision?.path || [];
  const selectedEndpoints = new Set([source, destination]);
  const l2Controls = visibleLinks.filter(isPrimaryL2Link);

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

  return (
    <section className="topology-page" data-testid="topology-canvas">
      <div className="topology-toolbar">
        <div>
          <h2>Sơ đồ logic mạng doanh nghiệp · v7</h2>
          <p>
            HQ + Branch · 2-tier collapsed Core/Distribution · VLAN 93 dùng MPLS L2VPN Primary/Backup ·
            routed intersite dùng IPsec L3 abstraction.
          </p>
        </div>
        <div className="topology-runtime-note">
          <strong>Simulation honesty</strong>
          <span>Firewall HA = 1 active namespace/pair; IPsec = routed behavior; MPLS = L2 bridge abstraction.</span>
        </div>
      </div>

      <div className="topology-svg-wrap">
        <svg viewBox="0 0 1900 820" role="img" aria-label="CCH Enterprise v7 topology">
          <rect x="30" y="90" width="1250" height="650" rx="20" fill="none" stroke="#d0d5dd" strokeDasharray="8 6" />
          <text x="50" y="120" fontSize="18" fontWeight="700">HQ</text>
          <rect x="1285" y="330" width="590" height="410" rx="20" fill="none" stroke="#d0d5dd" strokeDasharray="8 6" />
          <text x="1305" y="360" fontSize="18" fontWeight="700">BRANCH</text>
          <rect x="720" y="330" width="520" height="240" rx="18" fill="none" stroke="#f79009" strokeDasharray="6 6" />
          <text x="740" y="355" fontSize="14" fontWeight="700">WAN SERVICES</text>

          {visibleLinks.map((link) => {
            const from = positions[link.source];
            const to = positions[link.target];
            if (!from || !to) return null;
            const backup = isBackupLink(link);
            const standby = link.status === "standby" || (backup && link.status === "down" && !failedLinks.includes(link.id));
            const down = failedLinks.includes(link.id) || (link.status === "down" && !standby);
            const active = linkIsActive(path, link.source, link.target);
            return (
              <line
                key={link.id}
                x1={from[0] + 70}
                y1={from[1]}
                x2={to[0] + 70}
                y2={to[1]}
                stroke={down ? "#d92d20" : active ? "#1570ef" : standby ? "#7f56d9" : "#98a2b3"}
                strokeWidth={active ? 4 : 2}
                strokeDasharray={standby || down ? "8 6" : undefined}
                opacity={down ? 0.65 : standby ? 0.8 : 1}
              />
            );
          })}

          {nodes.map((node) => {
            const position = positions[node.id];
            if (!position) return null;
            const style = nodeStyle[nodeType(node)] || nodeStyle.service;
            const endpoint = endpointForNode(node);
            const selected = endpoint ? selectedEndpoints.has(endpoint) : false;
            return (
              <g
                key={node.id}
                transform={`translate(${position[0]}, ${position[1] - 28})`}
                role={endpoint ? "button" : undefined}
                tabIndex={endpoint ? 0 : undefined}
                onClick={() => {
                  if (!endpoint) return;
                  if (source === endpoint) onDestination(endpoint);
                  else onSource(endpoint);
                }}
              >
                <rect
                  width="140"
                  height="56"
                  rx="10"
                  fill={style.fill}
                  stroke={selected ? "#101828" : style.stroke}
                  strokeWidth={selected ? 3 : 1.8}
                />
                <text x="70" y="22" textAnchor="middle" fontSize="11" fontWeight="700" fill="#101828">
                  {String(node.label || node.id).slice(0, 24)}
                </text>
                <text x="70" y="40" textAnchor="middle" fontSize="8.5" fill="#475467">
                  {nodeSubtitle(node).slice(0, 34)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="topology-v7-legend">
        <span><strong>VLAN 93:</strong> gateway 10.10.93.1 chỉ ở HQ; Branch không có SVI.</span>
        <span><strong>L2VPN:</strong> CE1/Primary active, CE2/Backup standby để tránh loop L2.</span>
        <span><strong>IPsec:</strong> dashboard chỉ chứng minh routed path, không chứng minh mã hóa IPsec thật.</span>
        <span><strong>Partner:</strong> CRM/PBX nằm ngoài Server Farm nội bộ.</span>
      </div>

      <div className="topology-link-controls" aria-label="L2VPN primary path controls">
        {l2Controls.map((link) => {
          const down = failedLinks.includes(link.id) || link.status === "down";
          const busy = linkOperation?.linkId === link.id && linkOperation.status === "running";
          return (
            <button
              type="button"
              key={link.id}
              disabled={!authenticated || !liveLinkControl || busy}
              onClick={() => (down ? onRecover(link.id) : onFail(link.id))}
            >
              {down ? "Recover Primary" : "Fail Primary"} · {link.source} ↔ {link.target}
            </button>
          );
        })}
      </div>
    </section>
  );
}
