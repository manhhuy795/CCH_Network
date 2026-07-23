import {
  Activity,
  Bell,
  ChartNoAxesCombined,
  CircleHelp,
  LogOut,
  Menu,
  Network,
  PanelsTopLeft,
  Route,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { useState } from "react";
import type { AuthUser } from "../../api/client";
import { realtimeStatusLabel, realtimeStatusTone, type RealtimeConnectionState } from "../RealtimePanel";
import StatusBadge from "../ui/StatusBadge";

export type DashboardPage = "overview" | "topology" | "testing" | "policy" | "performance" | "events";

const navigation: Array<{ id: DashboardPage; label: string; icon: typeof PanelsTopLeft }> = [
  { id: "overview", label: "Tổng quan", icon: PanelsTopLeft },
  { id: "topology", label: "Topology", icon: Network },
  { id: "testing", label: "Kiểm tra kết nối", icon: Route },
  { id: "policy", label: "Chính sách & OpenFlow", icon: ShieldCheck },
  { id: "performance", label: "Hiệu năng", icon: ChartNoAxesCombined },
  { id: "events", label: "Sự kiện & nhật ký", icon: Bell },
];

type Props = {
  page: DashboardPage;
  onPage: (page: DashboardPage) => void;
  overallStatus: string;
  websocketState: RealtimeConnectionState;
  user?: AuthUser;
  authChecking: boolean;
  onLogout: () => void;
  onHelp: () => void;
  children: React.ReactNode;
};

export default function AppShell(props: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const [userMenu, setUserMenu] = useState(false);
  const visibleNavigation = props.user ? navigation.filter((item) => {
    if (props.user?.role === "admin" || props.user?.role === "operator") return true;
    if (props.user?.role === "viewer") return item.id !== "testing" && item.id !== "events";
    return item.id === "overview" || item.id === "events";
  }) : [];
  return (
    <div className={collapsed ? "app-shell sidebar-collapsed" : "app-shell"}>
      <aside className="app-sidebar">
        <div className="brand-block">
          <Activity size={22} aria-hidden="true" />
          {!collapsed && <div><strong>CCH Network</strong><span>SDN Operations</span></div>}
          <button className="icon-button sidebar-toggle" title="Thu gọn điều hướng" onClick={() => setCollapsed((value) => !value)}><Menu size={18} /></button>
        </div>
        <nav aria-label="Điều hướng chính">
          {visibleNavigation.map((item) => {
            const Icon = item.icon;
            return (
              <button className={props.page === item.id ? "nav-item active" : "nav-item"} key={item.id} onClick={() => props.onPage(item.id)} title={collapsed ? item.label : undefined}>
                <Icon size={18} aria-hidden="true" />
                {!collapsed && <span>{item.label}</span>}
              </button>
            );
          })}
        </nav>
        {!collapsed && <div className="sidebar-foot"><span>Hybrid MPLS L3VPN Logic</span><span>SDN Edge Policy</span></div>}
      </aside>
      <div className="app-stage">
        <header className="app-header">
          <div className="system-title">
            <strong>Call Center BPO Network Operations</strong>
            <span>Hybrid MPLS L3VPN Logic Simulation + SDN Edge Policy</span>
          </div>
          <div className="header-status">
            <StatusBadge status={props.overallStatus} />
            <StatusBadge status={realtimeStatusTone(props.websocketState)} label={realtimeStatusLabel(props.websocketState)} />
            <StatusBadge status={props.user ? "online" : "unknown"} label={props.user ? `Đã đăng nhập · ${props.user.role}` : "Chưa đăng nhập"} />
          </div>
          <div className="header-tools">
            <button className="icon-button" title="Trợ giúp" onClick={props.onHelp}><CircleHelp size={18} /></button>
            <div className="user-menu">
              <button className="icon-button" title="Tài khoản" onClick={() => setUserMenu((value) => !value)}><UserRound size={18} /></button>
              {userMenu && (
                <div className="user-popover">
                  <strong>{props.user?.username || "Khách"}</strong>
                  <span>{props.user ? `Role: ${props.user.role}` : (props.authChecking ? "Đang kiểm tra phiên" : "Chưa đăng nhập")}</span>
                  {props.user && <button onClick={() => { setUserMenu(false); props.onLogout(); }}><LogOut size={15} />Đăng xuất</button>}
                </div>
              )}
            </div>
          </div>
        </header>
        <main className="app-content">{props.children}</main>
      </div>
    </div>
  );
}
