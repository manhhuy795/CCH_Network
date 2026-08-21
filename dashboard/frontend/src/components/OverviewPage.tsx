import {
  Activity,
  AlertTriangle,
  Check,
  CheckCircle2,
  Clock3,
  DatabaseZap,
  MonitorDot,
  Play,
  RefreshCw,
  Route,
  Server,
  ShieldCheck,
  Waypoints,
} from "lucide-react";
import type { CSSProperties } from "react";
import type { ActivityEvent, DashboardPreflight, DashboardPreflightCase, Topology } from "../api/client";
import type { DashboardPage } from "./layout/AppShell";
import StatusBadge from "./ui/StatusBadge";

type HealthComponent = {
  status?: string;
  latency_ms?: number | null;
  message_vi?: string;
};

const requiredRuntimeComponents = [
  "controller",
  "backend",
  "mininet_topology",
  "mininet_control_agent",
  "openvswitch",
] as const;

type StatusTone = "online" | "degraded" | "offline" | "unknown";

export default function OverviewPage({
  components,
  onlineHosts,
  totalHosts,
  failedLinks,
  lastError,
  lastUpdated,
  topology,
  preflight,
  events,
  onNavigate,
  onRefresh,
}: {
  components: Record<string, HealthComponent>;
  onlineHosts: number;
  totalHosts: number;
  failedLinks: string[];
  lastError?: string;
  lastUpdated: string;
  topology?: Topology;
  preflight?: DashboardPreflight;
  events: ActivityEvent[];
  onNavigate: (page: DashboardPage) => void;
  onRefresh: () => void;
}) {
  const runtimeReady = requiredRuntimeComponents.filter((key) => components[key]?.status === "online").length;
  const l2vpn = topology?.l2vpn || {};
  const configuredVlan = Number(l2vpn.customer_vlan);
  const vlan = Number.isFinite(configuredVlan) ? configuredVlan : 40;
  const l2vpnConfigured = topology?.summary.l2vpn_service_count === 1 && vlan === 40;
  const l2vpnLinkIds = new Set((topology?.links || []).filter((link) => link.type === "l2vpn").map((link) => link.id));
  const failedAttachments = failedLinks.filter((linkId) => l2vpnLinkIds.has(linkId));
  const summary = preflight?.summary || {};
  const preflightCases = preflight?.cases || [];
  const l2Cases = preflightCases.filter((item) => item.id.startsWith("vlan40_"));
  const l2Passed = l2Cases.filter((item) => item.passed).length;
  const hasL2Evidence = l2vpnConfigured && l2Cases.length === 2;
  const measuredOnline = numberOr(summary.endpoints_online, onlineHosts);
  const measuredTotal = numberOr(summary.endpoints_total, totalHosts);
  const switchesReady = numberOr(summary.switches_ready, 0);
  const switchesExpected = numberOr(summary.switches_expected, topology?.summary.controlled_ovs_count || 8);
  const flowEntries = numberOr(summary.flow_entries, 0);
  const checksPassed = numberOr(summary.checks_passed, 0);
  const checksTotal = numberOr(summary.checks_total, 0);
  const preflightAvailable = Boolean(preflight?.available && preflightCases.length);
  const preflightPassed = preflightAvailable && preflight?.status === "passed" && !preflight?.stale;
  const allHostsOnline = measuredTotal > 0 && measuredOnline === measuredTotal;
  const serviceDown = failedAttachments.length > 0 || (hasL2Evidence && l2Passed < l2Cases.length);
  const serviceTone: StatusTone = serviceDown ? "offline" : hasL2Evidence && l2Passed === 2 ? "online" : "unknown";
  const activeTransport = l2vpnConfigured ? "VPWS / E-Line" : "Chưa xác nhận";
  const serviceLabel = serviceDown ? "Đường dịch vụ lỗi" : hasL2Evidence ? `${l2Passed}/2 chiều đạt` : "Chờ preflight";
  const coveragePercent = checksTotal > 0
    ? Math.round((checksPassed / checksTotal) * 100)
    : Math.round((runtimeReady / requiredRuntimeComponents.length) * 100);
  const sampleLabel = formatSampleAge(preflight);

  return (
    <div className="overview-page">
      <div className="overview-heading">
        <div>
          <h1>Tổng quan hệ thống</h1>
          <p>Mininet namespaces · OpenFlow inventory · VPWS VLAN 40 · cập nhật UI {lastUpdated || "chưa có dữ liệu"}</p>
        </div>
        <div className="overview-heading-actions">
          <button onClick={onRefresh}><RefreshCw size={16} />Làm mới</button>
          <button className="primary" onClick={() => onNavigate("testing")}><Play size={16} />Kiểm tra thủ công</button>
        </div>
      </div>

      <section className="overview-metrics" aria-label="Số liệu vận hành chính">
        <Metric icon={MonitorDot} label="Endpoint Mininet" value={`${measuredOnline}/${measuredTotal}`} note={preflightAvailable ? "Đọc từ namespace inventory" : "Chưa có mẫu preflight"} tone={allHostsOnline ? "online" : "degraded"} />
        <Metric icon={DatabaseZap} label="OpenFlow inventory" value={preflightAvailable ? `${flowEntries} entries` : "Chờ preflight"} note={`${switchesReady}/${switchesExpected} bridge OVS`} tone={!preflightAvailable ? "unknown" : switchesReady === switchesExpected && flowEntries > 0 ? "online" : "degraded"} />
        <Metric icon={Waypoints} label={`VLAN ${vlan} · VPWS`} value={hasL2Evidence ? `${l2Passed}/2 phép thử` : "Chờ mẫu đo"} note="HQ ↔ Branch Telesale" tone={serviceTone} />
        <Metric icon={AlertTriangle} label="Cảnh báo liên kết" value={failedLinks.length ? `${failedLinks.length} link down` : "0 liên kết lỗi"} note={failedLinks.length ? failedLinks.join(", ") : "Control Agent không ghi nhận lỗi"} tone={failedLinks.length ? "degraded" : "online"} />
      </section>

      <div className="overview-workspace">
        <div className="overview-main">
          <section className="service-path-panel">
            <div className="overview-panel-heading">
              <div className="overview-panel-title"><span><Route size={17} /></span><div><h2>Đường dịch vụ Project C</h2><p>VLAN {vlan} · cùng broadcast domain tại HQ và Branch Telesale</p></div></div>
              <div className="service-path-actions"><StatusBadge status={serviceTone} label={serviceLabel} /><button onClick={() => onNavigate("topology")}>Mở Topology</button></div>
            </div>

            <svg className="overview-path" viewBox="0 0 820 280" role="img" aria-labelledby="service-path-title service-path-desc">
              <title id="service-path-title">Đường dịch vụ VLAN {vlan} Project C</title>
              <desc id="service-path-desc">VLAN 40 đi từ Distribution HQ 2 qua CE HQ, dịch vụ carrier VPWS, CE Branch và Distribution Branch.</desc>
              <rect className="overview-site" x="12" y="42" width="182" height="190" rx="15" />
              <rect className="overview-site" x="626" y="42" width="182" height="190" rx="15" />
              <text x="30" y="69">HQ</text><text className="overview-svg-muted" x="30" y="90">Project C</text>
              <text x="644" y="69">Branch Telesale</text><text className="overview-svg-muted" x="644" y="90">Project C</text>
              <path className="overview-path-track" d="M144 151 C247 151 283 112 410 112 C537 112 572 151 676 151" />
              <path className={`overview-l2vpn-path${serviceDown ? " failed" : ""}`} d="M144 151 C247 151 283 112 410 112 C537 112 572 151 676 151" />
              <rect className="overview-endpoint" x="40" y="118" width="104" height="66" rx="11" />
              <text x="92" y="143" textAnchor="middle">Access HQ</text><text className="overview-svg-muted" x="92" y="164" textAnchor="middle">802.1Q · VLAN {vlan}</text>
              <rect className="overview-pe" x="199" y="116" width="92" height="70" rx="11" />
              <text x="245" y="144" textAnchor="middle">CE HQ</text><text className="overview-svg-muted" x="245" y="165" textAnchor="middle">AC · VLAN {vlan}</text>
              <path className="overview-cloud" d="M351 80 C367 56 397 54 417 70 C437 50 476 63 477 92 C500 100 497 133 472 138 L357 138 C328 137 326 96 351 80 Z" />
              <text x="413" y="97" textAnchor="middle">Carrier L2VPN</text><text className="overview-svg-muted" x="413" y="119" textAnchor="middle">VPWS / E-Line logic</text>
              <rect className="overview-pe" x="529" y="116" width="92" height="70" rx="11" />
              <text x="575" y="144" textAnchor="middle">CE Branch</text><text className="overview-svg-muted" x="575" y="165" textAnchor="middle">AC · VLAN {vlan}</text>
              <rect className="overview-endpoint" x="676" y="118" width="104" height="66" rx="11" />
              <text x="728" y="143" textAnchor="middle">Access BR</text><text className="overview-svg-muted" x="728" y="164" textAnchor="middle">802.1Q · VLAN {vlan}</text>
              <rect className="overview-service-chip" x="350" y="18" width="126" height="28" rx="14" /><text className="overview-service-chip-text" x="413" y="37" textAnchor="middle">CCH-PROJECT-C</text>
            </svg>

            <div className="service-facts">
              <Fact icon={CheckCircle2} value={activeTransport} label="Loại hình dịch vụ" />
              <Fact icon={Server} value={String(l2vpn.runtime_bridge || "Chưa có")} label="Bridge mô phỏng" />
              <Fact icon={ShieldCheck} value={hasL2Evidence ? `${l2Passed}/2 chiều` : "Chưa đo"} label="Kiểm thử hai chiều" />
            </div>
          </section>

          <section className="preflight-panel">
            <div className="overview-panel-heading">
              <div className="overview-panel-title"><span><Activity size={17} /></span><div><h2>Mininet preflight</h2><p>Kiểm thử không thay đổi topology · {sampleLabel}</p></div></div>
              <StatusBadge status={!preflightAvailable ? "unknown" : preflightPassed ? "online" : "degraded"} label={preflightAvailable ? `${checksPassed}/${checksTotal} đạt` : "Chưa chạy"} />
            </div>
            {preflightCases.length ? (
              <div className="preflight-cases">
                {preflightCases.map((item) => <PreflightRow item={item} key={item.id} />)}
              </div>
            ) : (
              <div className="preflight-empty"><Clock3 size={18} /><div><strong>Chưa có dữ liệu kiểm thử khởi động</strong><small>Chạy scripts/mininet_dashboard_preflight.py sau khi topology Mininet đã sẵn sàng.</small></div></div>
            )}
            <div className="preflight-source">Nguồn: {preflight?.source || "Mininet Control Agent + ovs-ofctl"}</div>
          </section>
        </div>

        <aside className="overview-side">
          <section className="service-health-panel">
            <div><h2>Bằng chứng runtime</h2><p>Số đo và cổng kiểm tra, không dùng trạng thái suy đoán</p></div>
            <div className="health-summary">
              <div className="health-ring" style={{ "--health": `${coveragePercent}%` } as CSSProperties}><strong>{coveragePercent}%</strong><small>độ phủ test</small></div>
              <dl>
                <div><dt>Preflight</dt><dd>{checksTotal ? `${checksPassed}/${checksTotal}` : "chưa chạy"}</dd></div>
                <div><dt>Endpoints</dt><dd>{measuredOnline}/{measuredTotal}</dd></div>
                <div><dt>OpenFlow</dt><dd>{flowEntries ? `${flowEntries} entries` : "chưa đo"}</dd></div>
              </dl>
            </div>
            <div className="health-checks">
              <HealthCheck ok={components.controller?.status === "online"} title="OS-Ken controller" detail={componentEvidence(components.controller, "6653/TCP")} />
              <HealthCheck ok={switchesReady > 0 && switchesReady === switchesExpected} title="Open vSwitch" detail={preflightAvailable ? `${switchesReady}/${switchesExpected} bridge · ${flowEntries} flow` : "Chờ inventory ovs-ofctl"} />
              <HealthCheck ok={hasL2Evidence && l2Passed === 2} title="VLAN 40 continuity" detail={hasL2Evidence ? `${l2Passed}/2 hướng ping đạt` : "Chưa chạy phép đo HQ ↔ Branch"} />
              <HealthCheck ok={!failedLinks.length} title="Link state" detail={failedLinks.length ? `${failedLinks.length} link đang down` : "0 link down trong Control Agent"} />
            </div>
          </section>

          <section className="recent-activity-panel">
            <h2>Nhật ký gần nhất</h2>
            {events.slice(0, 3).map((event) => <EventRow event={event} key={event.id} />)}
            {!events.length && <p className="empty-activity">Chưa có thao tác trong phiên hiện tại.</p>}
            {lastError && <button className="latest-error-link" onClick={() => onNavigate("events")}><AlertTriangle size={15} />{lastError}</button>}
          </section>
        </aside>
      </div>
    </div>
  );
}

function numberOr(value: number | undefined, fallback: number) {
  return Number.isFinite(value) ? Number(value) : fallback;
}

function formatSampleAge(preflight?: DashboardPreflight) {
  if (!preflight?.available) return "chưa có mẫu đo";
  const age = preflight.age_seconds;
  if (age == null) return preflight.checked_at ? new Date(preflight.checked_at).toLocaleString("vi-VN") : "không rõ thời điểm";
  if (age < 60) return `${age} giây trước`;
  if (age < 3600) return `${Math.floor(age / 60)} phút trước`;
  return `${Math.floor(age / 3600)} giờ trước${preflight.stale ? " · mẫu cũ" : ""}`;
}

function componentEvidence(component: HealthComponent | undefined, fallback: string) {
  if (!component) return fallback;
  const latency = typeof component.latency_ms === "number" ? ` · ${component.latency_ms} ms` : "";
  return `${fallback}${latency}`;
}

function Metric({ icon: Icon, label, value, note, tone }: { icon: typeof Activity; label: string; value: string; note: string; tone: StatusTone }) {
  return <div className="overview-metric"><span className="overview-metric-icon"><Icon size={17} /></span><div><span className={`metric-label ${tone}`}><i />{label}</span><strong>{value}</strong><small title={note}>{note}</small></div></div>;
}

function Fact({ icon: Icon, value, label }: { icon: typeof Activity; value: string; label: string }) {
  return <div><Icon size={17} /><span><strong>{value}</strong><small>{label}</small></span></div>;
}

function HealthCheck({ ok, title, detail }: { ok: boolean; title: string; detail: string }) {
  const Icon = ok ? Check : AlertTriangle;
  return <div className={ok ? "health-check ok" : "health-check warning"}><span><Icon size={14} /></span><div><strong>{title}</strong><small>{detail}</small></div></div>;
}

function PreflightRow({ item }: { item: DashboardPreflightCase }) {
  const measured = item.expectation === "deny"
    ? `${item.packet_loss_percent ?? 100}% loss · blocked`
    : item.avg_rtt_ms != null
      ? `${item.avg_rtt_ms.toFixed(2)} ms RTT · ${item.packet_loss_percent ?? 0}% loss`
      : item.observed;
  return (
    <div className={item.passed ? "preflight-row passed" : "preflight-row failed"}>
      <span className="preflight-result-icon">{item.passed ? <Check size={14} /> : <AlertTriangle size={14} />}</span>
      <div className="preflight-case-name"><strong>{item.label}</strong><small>{item.source} → {item.destination} · expected {item.expectation}</small></div>
      <div className="preflight-measure"><strong>{measured}</strong><small>{item.evidence}</small></div>
    </div>
  );
}

function EventRow({ event }: { event: ActivityEvent }) {
  const Icon = event.severity === "error" ? AlertTriangle : Activity;
  return <div className="overview-event"><span><Icon size={15} /></span><div><strong>{event.message}</strong><small>{event.component} · {event.event_type}</small></div><time>{new Date(event.timestamp).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}</time></div>;
}
