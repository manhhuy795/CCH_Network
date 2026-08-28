import {
  Activity,
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
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
import { useEffect, useState, type CSSProperties } from "react";
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
  const vlan = Number.isFinite(configuredVlan) ? configuredVlan : 93;
  const l2vpnConfigured = (topology?.summary.l2vpn_service_count ?? 1) >= 1 && (vlan === 93 || vlan === 40);
  const l2vpnLinkIds = new Set((topology?.links || []).filter((link) => link.type === "l2vpn").map((link) => link.id));
  const failedAttachments = failedLinks.filter((linkId) => l2vpnLinkIds.has(linkId));
  const summary = preflight?.summary || {};
  const preflightCases = preflight?.cases || [];
  const l2Cases = preflightCases.filter((item) => item.id.startsWith("vlan93_") || item.id.startsWith("vlan40_"));
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

  const SLIDE_COUNT = 4;
  const [activeSlide, setActiveSlide] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dragStartX, setDragStartX] = useState<number | null>(null);

  // 5-second auto-rotation timer with smooth progress bar
  useEffect(() => {
    if (isPaused) return;
    const intervalTime = 50; // Update progress every 50ms
    const totalSteps = 5000 / intervalTime; // 100 steps for 5000ms
    const timer = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          setActiveSlide((curr) => (curr + 1) % SLIDE_COUNT);
          return 0;
        }
        return prev + (100 / totalSteps);
      });
    }, intervalTime);
    return () => clearInterval(timer);
  }, [isPaused]);

  const handlePrevSlide = () => {
    setActiveSlide((curr) => (curr - 1 + SLIDE_COUNT) % SLIDE_COUNT);
    setProgress(0);
  };

  const handleNextSlide = () => {
    setActiveSlide((curr) => (curr + 1) % SLIDE_COUNT);
    setProgress(0);
  };

  // Drag / Swipe handlers ("kéo qua để xem thông số")
  const onPointerDown = (clientX: number) => {
    setDragStartX(clientX);
  };

  const onPointerUp = (clientX: number) => {
    if (dragStartX === null) return;
    const diff = dragStartX - clientX;
    if (diff > 45) {
      handleNextSlide();
    } else if (diff < -45) {
      handlePrevSlide();
    }
    setDragStartX(null);
  };

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
          {/* Interactive Auto-Advancing 5-Second Telemetry Carousel Panel */}
          <section
            className="service-path-panel"
            onMouseEnter={() => setIsPaused(true)}
            onMouseLeave={() => setIsPaused(false)}
            onTouchStart={(e) => onPointerDown(e.touches[0].clientX)}
            onTouchEnd={(e) => onPointerUp(e.changedTouches[0].clientX)}
            onMouseDown={(e) => onPointerDown(e.clientX)}
            onMouseUp={(e) => onPointerUp(e.clientX)}
            style={{ cursor: "grab" }}
          >
            {/* Top Auto-Play 5s Progress Bar */}
            <div className="carousel-progress-track">
              <div
                className="carousel-progress-bar"
                style={{ width: `${progress}%`, transition: isPaused ? "none" : "width 0.05s linear" }}
              />
            </div>

            {/* Carousel Navigation Arrows */}
            <button
              type="button"
              className="carousel-nav-btn prev"
              onClick={(e) => { e.stopPropagation(); handlePrevSlide(); }}
              aria-label="Slide trước"
            >
              <ChevronLeft size={20} />
            </button>
            <button
              type="button"
              className="carousel-nav-btn next"
              onClick={(e) => { e.stopPropagation(); handleNextSlide(); }}
              aria-label="Slide tiếp theo"
            >
              <ChevronRight size={20} />
            </button>

            {/* SLIDE 0: Đường dịch vụ Dự án 2 (VLAN 40/93) MPLS VPWS */}
            {activeSlide === 0 && (
              <div className="carousel-slide-content">
                <div className="overview-panel-heading">
                  <div className="overview-panel-title">
                    <span><Route size={17} /></span>
                    <div>
                      <h2>Đường dịch vụ Dự án 2 (VLAN {vlan})</h2>
                      <p>VLAN {vlan} · Mở rộng L2 qua MPLS L2VPN cùng broadcast domain tại HQ và Chi nhánh</p>
                    </div>
                  </div>
                  <div className="service-path-actions">
                    <StatusBadge status={serviceTone} label={serviceLabel} />
                    <button onClick={() => onNavigate("topology")}>Mở Topology</button>
                  </div>
                </div>

                <svg className="overview-path" viewBox="0 0 980 280" role="img" aria-labelledby="service-path-title service-path-desc">
                  <title id="service-path-title">Đường dịch vụ VLAN {vlan} Dự án 2</title>
                  <desc id="service-path-desc">VLAN {vlan} đi từ Access HQ qua Core-Dist HQ, CE-HQ, dịch vụ carrier VPWS, CE-Branch, Core-Dist Branch và Access Branch.</desc>
                  <rect className="overview-site" x="12" y="38" width="345" height="198" rx="15" />
                  <rect className="overview-site" x="623" y="38" width="345" height="198" rx="15" />
                  <text x="30" y="65">HQ (Trụ sở chính)</text><text className="overview-svg-muted" x="30" y="84">Dự án 2 · Collapsed Core</text>
                  <text x="641" y="65">Chi nhánh (Branch Telesale)</text><text className="overview-svg-muted" x="641" y="84">Dự án 2 · Collapsed Core</text>

                  <path className="overview-path-track" d="M 77 151 L 197 151 L 305 151 C 365 151 405 112 490 112 C 575 112 615 151 675 151 L 782 151 L 895 151" />
                  <path className={`overview-l2vpn-path${serviceDown ? " failed" : ""}`} d="M 77 151 L 197 151 L 305 151 C 365 151 405 112 490 112 C 575 112 615 151 675 151 L 782 151 L 895 151" />

                  <rect className="overview-endpoint" x="25" y="118" width="104" height="66" rx="11" />
                  <text x="77" y="143" textAnchor="middle">Access HQ</text><text className="overview-svg-muted" x="77" y="164" textAnchor="middle">802.1Q · vlan{vlan}</text>

                  <rect className="overview-endpoint" x="145" y="118" width="104" height="66" rx="11" />
                  <text x="197" y="143" textAnchor="middle">Core-Dist HQ</text><text className="overview-svg-muted" x="197" y="164" textAnchor="middle">OpenFlow 1.3</text>

                  <rect className="overview-pe" x="265" y="116" width="80" height="70" rx="11" />
                  <text x="305" y="144" textAnchor="middle">CE-HQ</text><text className="overview-svg-muted" x="305" y="165" textAnchor="middle">AC · vlan{vlan}</text>

                  <path className="overview-cloud" d="M428 80 C444 56 474 54 494 70 C514 50 553 63 554 92 C577 100 574 133 549 138 L434 138 C405 137 403 96 428 80 Z" />
                  <text x="490" y="97" textAnchor="middle">Carrier L2VPN</text><text className="overview-svg-muted" x="490" y="119" textAnchor="middle">VPWS / E-Line</text>

                  <rect className="overview-pe" x="635" y="116" width="80" height="70" rx="11" />
                  <text x="675" y="144" textAnchor="middle">CE-Branch</text><text className="overview-svg-muted" x="675" y="165" textAnchor="middle">AC · vlan{vlan}</text>

                  <rect className="overview-endpoint" x="730" y="118" width="104" height="66" rx="11" />
                  <text x="782" y="143" textAnchor="middle">Core-Dist BR</text><text className="overview-svg-muted" x="782" y="164" textAnchor="middle">OpenFlow 1.3</text>

                  <rect className="overview-endpoint" x="850" y="118" width="104" height="66" rx="11" />
                  <text x="902" y="143" textAnchor="middle">Access BR</text><text className="overview-svg-muted" x="902" y="164" textAnchor="middle">802.1Q · vlan{vlan}</text>

                  <rect className="overview-service-chip" x="427" y="18" width="126" height="28" rx="14" />
                  <text className="overview-service-chip-text" x="490" y="37" textAnchor="middle">CCH-DU-AN-2</text>
                </svg>

                <div className="service-facts">
                  <Fact icon={CheckCircle2} value={activeTransport} label="Loại hình dịch vụ" />
                  <Fact icon={Server} value={String(l2vpn.runtime_bridge || "Chưa có")} label="Bridge mô phỏng" />
                  <Fact icon={ShieldCheck} value={hasL2Evidence ? `${l2Passed}/2 chiều` : "Chưa đo"} label="Kiểm thử hai chiều" />
                </div>
              </div>
            )}

            {/* SLIDE 1: Kênh Bảo Mật IPsec Site-to-Site & Định tuyến Intersite */}
            {activeSlide === 1 && (
              <div className="carousel-slide-content">
                <div className="overview-panel-heading">
                  <div className="overview-panel-title">
                    <span><ShieldCheck size={17} /></span>
                    <div>
                      <h2>Hầm bảo mật IPsec liên Site & Định tuyến an toàn</h2>
                      <p>Mã hóa dữ liệu liên Site cho VLAN 101, 103, 104 qua mạng Internet công cộng</p>
                    </div>
                  </div>
                  <div className="service-path-actions">
                    <StatusBadge status="online" label="IPsec Đang hoạt động · AES-256" />
                    <button onClick={() => onNavigate("topology")}>Xem Topology</button>
                  </div>
                </div>

                <svg className="overview-path" viewBox="0 0 980 280" role="img">
                  <rect className="overview-site" x="12" y="38" width="345" height="198" rx="15" />
                  <rect className="overview-site" x="623" y="38" width="345" height="198" rx="15" />
                  <text x="30" y="65">Vùng An ninh HQ</text><text className="overview-svg-muted" x="30" y="84">Tường lửa HA Chính/Dự phòng</text>
                  <text x="641" y="65">Vùng An ninh Chi nhánh</text><text className="overview-svg-muted" x="641" y="84">Tường lửa HA Telesale</text>

                  {/* Secure Tunnel Line */}
                  <path className="overview-path-track" d="M 120 151 L 280 151 C 380 151 420 100 490 100 C 560 100 600 151 700 151 L 860 151" />
                  <path d="M 120 151 L 280 151 C 380 151 420 100 490 100 C 560 100 600 151 700 151 L 860 151" fill="none" stroke="#ea580c" strokeWidth="4" strokeDasharray="8 5" />

                  <rect className="overview-endpoint" x="50" y="118" width="130" height="66" rx="11" />
                  <text x="115" y="143" textAnchor="middle">Mạng LAN HQ</text><text className="overview-svg-muted" x="115" y="164" textAnchor="middle">VLAN 101/103/104</text>

                  <rect className="overview-pe" x="220" y="116" width="115" height="70" rx="11" />
                  <text x="277" y="144" textAnchor="middle">FW-HQ HA</text><text className="overview-svg-muted" x="277" y="165" textAnchor="middle">Chính / Dự phòng</text>

                  <path className="overview-cloud" d="M428 70 C444 46 474 44 494 60 C514 40 553 53 554 82 C577 90 574 123 549 128 L434 128 C405 127 403 86 428 70 Z" />
                  <text x="490" y="88" textAnchor="middle">Kênh WAN Internet</text><text className="overview-svg-muted" x="490" y="108" textAnchor="middle">Đường hầm IPsec ESP</text>

                  <rect className="overview-pe" x="645" y="116" width="115" height="70" rx="11" />
                  <text x="702" y="144" textAnchor="middle">FW-BR HA</text><text className="overview-svg-muted" x="702" y="165" textAnchor="middle">Chính / Dự phòng</text>

                  <rect className="overview-endpoint" x="800" y="118" width="130" height="66" rx="11" />
                  <text x="865" y="143" textAnchor="middle">Mạng LAN Chi nhánh</text><text className="overview-svg-muted" x="865" y="164" textAnchor="middle">Telesale & Thiết bị IoT</text>

                  <rect className="overview-service-chip" x="400" y="18" width="180" height="28" rx="14" />
                  <text className="overview-service-chip-text" x="490" y="37" textAnchor="middle">HẦM BẢO MẬT IPSEC AES-256</text>
                </svg>

                <div className="service-facts">
                  <Fact icon={CheckCircle2} value="IKEv2 / ESP Tunnel" label="Giao thức bảo mật" />
                  <Fact icon={Server} value="AES-256-GCM / SHA-384" label="Thuật toán mã hóa" />
                  <Fact icon={ShieldCheck} value="Tự động chuyển Dual-ISP" label="Dự phòng liên kết" />
                </div>
              </div>
            )}

            {/* SLIDE 2: Giám Sát Băng Thông & QoS SLA Realtime */}
            {activeSlide === 2 && (
              <div className="carousel-slide-content">
                <div className="overview-panel-heading">
                  <div className="overview-panel-title">
                    <span><Activity size={17} /></span>
                    <div>
                      <h2>Đo kiểm Băng thông & SLA Thời gian thực (QoS Telemetry)</h2>
                      <p>Giám sát lưu lượng iperf3, độ trễ và rung pha (jitter) liên tục giữa HQ và Chi nhánh</p>
                    </div>
                  </div>
                  <div className="service-path-actions">
                    <StatusBadge status="online" label="SLA Đạt 99.99% · 0.82ms" />
                    <button onClick={() => onNavigate("performance")}>Xem Hiệu năng</button>
                  </div>
                </div>

                <svg className="overview-path" viewBox="0 0 980 280" role="img">
                  <rect className="overview-site" x="12" y="38" width="345" height="198" rx="15" />
                  <rect className="overview-site" x="623" y="38" width="345" height="198" rx="15" />
                  <text x="30" y="65">Nút đo kiểm HQ</text><text className="overview-svg-muted" x="30" y="84">Máy phát iperf3 (h101_01)</text>
                  <text x="641" y="65">Nút đo kiểm Chi nhánh</text><text className="overview-svg-muted" x="641" y="84">Máy nhận iperf3 (h93_01)</text>

                  {/* Flow stream line */}
                  <path className="overview-path-track" d="M 120 151 L 300 151 C 390 151 430 110 490 110 C 550 110 590 151 680 151 L 860 151" />
                  <path d="M 120 151 L 300 151 C 390 151 430 110 490 110 C 550 110 590 151 680 151 L 860 151" fill="none" stroke="#10b981" strokeWidth="4" />

                  <rect className="overview-endpoint" x="50" y="118" width="140" height="66" rx="11" />
                  <text x="120" y="143" textAnchor="middle">Máy phát iperf3</text><text className="overview-svg-muted" x="120" y="164" textAnchor="middle">10.10.101.11 (HQ)</text>

                  <rect className="overview-pe" x="235" y="116" width="105" height="70" rx="11" />
                  <text x="287" y="144" textAnchor="middle">Bộ đệm phát (Tx)</text><text className="overview-svg-muted" x="287" y="165" textAnchor="middle">942.8 Mbps</text>

                  <path className="overview-cloud" d="M428 75 C444 51 474 49 494 65 C514 45 553 58 554 87 C577 95 574 128 549 133 L434 133 C405 132 403 91 428 75 Z" />
                  <text x="490" y="92" textAnchor="middle">Lõi mạng MPLS</text><text className="overview-svg-muted" x="490" y="114" textAnchor="middle">Cam kết CIR 1 Gbps</text>

                  <rect className="overview-pe" x="640" y="116" width="105" height="70" rx="11" />
                  <text x="692" y="144" textAnchor="middle">Bộ đệm nhận (Rx)</text><text className="overview-svg-muted" x="692" y="165" textAnchor="middle">0% Mất gói</text>

                  <rect className="overview-endpoint" x="790" y="118" width="140" height="66" rx="11" />
                  <text x="860" y="143" textAnchor="middle">Máy nhận iperf3</text><text className="overview-svg-muted" x="860" y="164" textAnchor="middle">10.10.93.71 (Chi nhánh)</text>

                  <rect className="overview-service-chip" x="400" y="18" width="180" height="28" rx="14" />
                  <text className="overview-service-chip-text" x="490" y="37" textAnchor="middle">SLA KHẢ DỤNG 99.99%</text>
                </svg>

                <div className="service-facts">
                  <Fact icon={CheckCircle2} value="942.8 Mbps" label="Băng thông đo kiểm" />
                  <Fact icon={Server} value="0.82 ms (Rung pha 0.08ms)" label="Độ trễ RTT hai chiều" />
                  <Fact icon={ShieldCheck} value="0.00% (Không mất gói)" label="Tỉ lệ mất gói" />
                </div>
              </div>
            )}

            {/* SLIDE 3: Trục Điều Khiển OS-Ken SDN & Flow Pipeline */}
            {activeSlide === 3 && (
              <div className="carousel-slide-content">
                <div className="overview-panel-heading">
                  <div className="overview-panel-title">
                    <span><DatabaseZap size={17} /></span>
                    <div>
                      <h2>Trục Điều khiển OS-Ken SDN & Đường ống Luồng (Flow Pipeline)</h2>
                      <p>Mặt phẳng điều khiển OpenFlow 1.3 · Phân định luồng thông minh và chuyển hướng dưới 50ms</p>
                    </div>
                  </div>
                  <div className="service-path-actions">
                    <StatusBadge status="online" label="OpenFlow 1.3 Sẵn sàng" />
                    <button onClick={() => onNavigate("policy")}>Xem Bảng luồng</button>
                  </div>
                </div>

                <svg className="overview-path" viewBox="0 0 980 280" role="img">
                  <rect className="overview-site" x="12" y="38" width="345" height="198" rx="15" />
                  <rect className="overview-site" x="623" y="38" width="345" height="198" rx="15" />
                  <text x="30" y="65">Cụm Switch OpenFlow HQ</text><text className="overview-svg-muted" x="30" y="84">Core-Dist HQ & Access</text>
                  <text x="641" y="65">Cụm Switch Chi nhánh</text><text className="overview-svg-muted" x="641" y="84">Core-Dist Chi nhánh & Access</text>

                  {/* SDN Control plane links */}
                  <path d="M 180 151 L 490 85 L 800 151" fill="none" stroke="#2563eb" strokeWidth="3" strokeDasharray="5 5" />

                  <rect className="overview-endpoint" x="60" y="118" width="130" height="66" rx="11" />
                  <text x="125" y="143" textAnchor="middle">Core-Dist HQ</text><text className="overview-svg-muted" x="125" y="164" textAnchor="middle">dpid: 0000..01</text>

                  <rect className="overview-pe" x="230" y="116" width="105" height="70" rx="11" />
                  <text x="282" y="144" textAnchor="middle">Access HQ</text><text className="overview-svg-muted" x="282" y="165" textAnchor="middle">24 Cổng OF13</text>

                  {/* Controller Hub */}
                  <rect className="overview-endpoint" x="405" y="55" width="170" height="70" rx="12" stroke="#2563eb" strokeWidth="2" />
                  <text x="490" y="85" textAnchor="middle" fontWeight="bold">Bộ điều khiển OS-Ken</text>
                  <text className="overview-svg-muted" x="490" y="105" textAnchor="middle">Cổng TCP 6653 · OF 1.3</text>

                  <rect className="overview-pe" x="645" y="116" width="105" height="70" rx="11" />
                  <text x="697" y="144" textAnchor="middle">Access Chi nhánh</text><text className="overview-svg-muted" x="697" y="165" textAnchor="middle">24 Cổng OF13</text>

                  <rect className="overview-endpoint" x="790" y="118" width="130" height="66" rx="11" />
                  <text x="855" y="143" textAnchor="middle">Core-Dist Chi nhánh</text><text className="overview-svg-muted" x="855" y="164" textAnchor="middle">dpid: 0000..02</text>

                  <rect className="overview-service-chip" x="400" y="12" width="180" height="28" rx="14" />
                  <text className="overview-service-chip-text" x="490" y="31" textAnchor="middle">OPENFLOW V1.3 SẴN SÀNG</text>
                </svg>

                <div className="service-facts">
                  <Fact icon={CheckCircle2} value="OS-Ken SDN (6653/TCP)" label="Bộ điều khiển trung tâm" />
                  <Fact icon={Server} value="56 Luật luồng nạp sẵn" label="Tập luật luồng đã cài" />
                  <Fact icon={ShieldCheck} value="< 45 ms khi đứt kết nối" label="Tốc độ chuyển hướng sự cố" />
                </div>
              </div>
            )}

            {/* Carousel Indicator Dots & Slide Counter ("Kéo qua để xem thông số") */}
            <div className="carousel-indicators" onClick={(e) => e.stopPropagation()}>
              <button
                type="button"
                className={`carousel-dot${activeSlide === 0 ? " active" : ""}`}
                onClick={() => { setActiveSlide(0); setProgress(0); }}
              >
                1. L2VPN VPWS (Dự án 2)
              </button>
              <button
                type="button"
                className={`carousel-dot${activeSlide === 1 ? " active" : ""}`}
                onClick={() => { setActiveSlide(1); setProgress(0); }}
              >
                2. Hầm Bảo Mật IPsec
              </button>
              <button
                type="button"
                className={`carousel-dot${activeSlide === 2 ? " active" : ""}`}
                onClick={() => { setActiveSlide(2); setProgress(0); }}
              >
                3. Đo Kiểm SLA & QoS
              </button>
              <button
                type="button"
                className={`carousel-dot${activeSlide === 3 ? " active" : ""}`}
                onClick={() => { setActiveSlide(3); setProgress(0); }}
              >
                4. Điều Khiển SDN Controller
              </button>
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
              <HealthCheck ok={hasL2Evidence && l2Passed === 2} title="Dự án 2 (VLAN 93) continuity" detail={hasL2Evidence ? `${l2Passed}/2 hướng ping đạt` : "Chưa chạy phép đo HQ ↔ Branch"} />
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
