import {
  Bell,
  ChartNoAxesCombined,
  CircleHelp,
  LogOut,
  Moon,
  Network,
  PanelsTopLeft,
  Route,
  Server,
  ShieldCheck,
  Sun,
  UserRound,
} from "lucide-react";
import { useEffect, useState } from "react";
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
  overallLabel?: string;
  websocketState: RealtimeConnectionState;
  user?: AuthUser;
  authChecking: boolean;
  onLogout: () => void;
  onHelp: () => void;
  children: React.ReactNode;
};

export default function AppShell(props: Props) {
  const [userMenu, setUserMenu] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">(() => localStorage.getItem("cch-theme") === "dark" ? "dark" : "light");
  const visibleNavigation = props.user ? navigation.filter((item) => {
    if (props.user?.role === "admin" || props.user?.role === "operator") return true;
    if (props.user?.role === "viewer") return item.id !== "testing" && item.id !== "events";
    return item.id === "overview" || item.id === "events";
  }) : [];
  const monitoringNavigation = visibleNavigation.filter((item) => item.id === "overview" || item.id === "topology" || item.id === "testing");
  const operationsNavigation = visibleNavigation.filter((item) => item.id === "policy" || item.id === "performance" || item.id === "events");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("cch-theme", theme);
  }, [theme]);

  const currentPage = navigation.find((item) => item.id === props.page)?.label || "Tổng quan";
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="brand-block">
          <span className="brand-mark"><Network size={17} aria-hidden="true" /></span>
          <div><strong>CCH Network</strong><span>Operations</span></div>
        </div>
        <nav aria-label="Điều hướng chính">
          <span className="nav-caption">Giám sát</span>
          {monitoringNavigation.map((item) => <NavItem {...item} active={props.page === item.id} key={item.id} onClick={() => props.onPage(item.id)} />)}
          <span className="nav-caption">Vận hành</span>
          {operationsNavigation.map((item) => <NavItem {...item} active={props.page === item.id} key={item.id} onClick={() => props.onPage(item.id)} />)}
        </nav>
        <div className="sidebar-workspace"><span className="workspace-icon"><Server size={15} /></span><span><strong>Mininet Lab</strong><small>Ubuntu · OpenFlow 1.3</small></span></div>
      </aside>
      <div className="app-stage">
        <header className="app-header">
          <div className="breadcrumbs"><span>CCH Network</span><span>/</span><strong>{currentPage}</strong></div>
          <div className="header-status">
            <StatusBadge status={props.overallStatus} label={props.overallLabel} />
            {(props.page === "testing" || props.page === "performance") && <StatusBadge status={realtimeStatusTone(props.websocketState)} label={realtimeStatusLabel(props.websocketState)} />}
          </div>
          <div className="header-tools">
            <span className="authenticated-label">{props.user ? `Đã đăng nhập · ${props.user.role}` : "Chưa đăng nhập"}</span>
            <button className="theme-toggle" aria-pressed={theme === "dark"} title={theme === "light" ? "Bật chế độ tối" : "Bật chế độ sáng"} onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
              {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}<span>{theme === "light" ? "Tối" : "Sáng"}</span>
            </button>
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

function NavItem({ label, icon: Icon, active, onClick }: typeof navigation[number] & { active: boolean; onClick: () => void }) {
  return <button className={active ? "nav-item active" : "nav-item"} onClick={onClick} aria-current={active ? "page" : undefined}><Icon size={17} aria-hidden="true" /><span>{label}</span></button>;
}
