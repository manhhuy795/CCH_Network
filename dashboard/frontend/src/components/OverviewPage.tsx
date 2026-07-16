import { ArrowRight, CircleAlert, Network, Route } from "lucide-react";
import type { DashboardPage } from "./layout/AppShell";
import StatusBadge from "./ui/StatusBadge";

type HealthComponent = { status?: string; message_vi?: string; error_code?: string | null };

export default function OverviewPage({
  components,
  onlineHosts,
  totalHosts,
  failedLinks,
  lastError,
  lastUpdated,
  onNavigate,
}: {
  components: Record<string, HealthComponent>;
  onlineHosts: number;
  totalHosts: number;
  failedLinks: string[];
  lastError?: string;
  lastUpdated: string;
  onNavigate: (page: DashboardPage) => void;
}) {
  const items = [
    ["controller", "Controller"],
    ["backend", "Backend"],
    ["mininet_topology", "Mininet"],
    ["mininet_control_agent", "Control Agent"],
    ["openvswitch", "Open vSwitch"],
    ["websocket", "WebSocket"],
  ] as const;
  return (
    <>
      <div className="page-heading">
        <div><h1>Tổng quan vận hành</h1><p>Cập nhật gần nhất: {lastUpdated || "chưa có dữ liệu"}</p></div>
      </div>
      <div className="overview-status-grid">
        {items.map(([key, label]) => {
          const item = components[key] || {};
          return (
            <div className="status-tile" key={key}>
              <strong>{label}</strong>
              <StatusBadge status={item.status || "unknown"} />
              <small>{item.message_vi || "Chưa có dữ liệu runtime."}</small>
              {item.error_code && <code>{item.error_code}</code>}
            </div>
          );
        })}
        <div className="status-tile">
          <strong>Host online</strong>
          <span>{onlineHosts}/{totalHosts}</span>
          <small>Endpoint được xác nhận trực tiếp từ Mininet.</small>
        </div>
        <div className="status-tile">
          <strong>Link/cảnh báo</strong>
          <StatusBadge status={failedLinks.length ? "degraded" : "online"} label={failedLinks.length ? `${failedLinks.length} link DOWN` : "Không có link DOWN"} />
          <small>{failedLinks.length ? failedLinks.join(", ") : "Các link logic đang ở trạng thái bình thường."}</small>
        </div>
      </div>
      <section className="overview-actions">
        <div className="section-title"><h2>Thao tác nhanh</h2><span>Đi tới workspace phù hợp</span></div>
        <div className="quick-actions">
          <button className="primary" onClick={() => onNavigate("testing")}><Route size={17} />Kiểm tra kết nối<ArrowRight size={15} /></button>
          <button onClick={() => onNavigate("topology")}><Network size={17} />Mở Topology<ArrowRight size={15} /></button>
          <button onClick={() => onNavigate("events")}><CircleAlert size={17} />Xem lỗi gần nhất<ArrowRight size={15} /></button>
        </div>
        <p className={lastError ? "latest-error" : "latest-error empty"}>
          {lastError || "Chưa có lỗi trong phiên dashboard hiện tại."}
        </p>
      </section>
    </>
  );
}
