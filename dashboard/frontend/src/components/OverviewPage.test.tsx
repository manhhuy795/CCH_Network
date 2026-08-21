import { fireEvent, render, screen } from "@testing-library/react";
import type { DashboardPreflight, Topology } from "../api/client";
import OverviewPage from "./OverviewPage";

const topology = {
  nodes: [], groups: [], hosts: [], links: [
    { id: "dist_hq_2-l2vpn_vpws40", source: "dist_hq_2", target: "l2vpn_vpws40", type: "l2vpn", status: "up" },
    { id: "l2vpn_vpws40-dist_branch", source: "l2vpn_vpws40", target: "dist_branch", type: "l2vpn", status: "up" },
  ], policy_map: {},
  l2vpn: { customer_vlan: 40, runtime_bridge: "l2vpn40", type: "VPWS / E-Line logic" },
  summary: { user_count: 0, service_count: 0, controlled_ovs_count: 0, l2vpn_service_count: 1 },
} satisfies Topology;

const preflight = {
  status: "passed",
  available: true,
  age_seconds: 12,
  stale: false,
  source: "Mininet Control Agent + ovs-ofctl OpenFlow13",
  summary: {
    checks_passed: 5, checks_total: 5, endpoints_online: 133, endpoints_total: 133,
    user_hosts_online: 110, switches_ready: 8, switches_expected: 8, flow_entries: 56,
  },
  cases: [
    { id: "vlan40_hq_to_branch", label: "VLAN 40 · HQ → Branch", source: "h40_01", destination: "h40_11", expectation: "allow", observed: "reachable", evidence: "VPWS forward", passed: true, avg_rtt_ms: 0.14, packet_loss_percent: 0 },
    { id: "vlan40_branch_to_hq", label: "VLAN 40 · Branch → HQ", source: "h40_11", destination: "h40_01", expectation: "allow", observed: "reachable", evidence: "VPWS return", passed: true, avg_rtt_ms: 0.16, packet_loss_percent: 0 },
    { id: "branch_voice_to_pbx", label: "Telesale → PBX/SBC", source: "h50_01", destination: "h90", expectation: "allow", observed: "reachable", evidence: "Voice", passed: true, avg_rtt_ms: 0.2, packet_loss_percent: 0 },
    { id: "project_segmentation", label: "Project C ↛ Project B", source: "h40_01", destination: "h30_01", expectation: "deny", observed: "blocked", evidence: "Isolation", passed: true, packet_loss_percent: 100 },
    { id: "guest_isolation", label: "Guest ↛ Project C", source: "guest_01", destination: "h40_01", expectation: "deny", observed: "blocked", evidence: "Guest isolation", passed: true, packet_loss_percent: 100 },
  ],
} satisfies DashboardPreflight;

const baseProps = {
  components: { controller: { status: "online", message_vi: "Controller sẵn sàng" } },
  onlineHosts: 110,
  totalHosts: 115,
  failedLinks: [] as string[],
  lastUpdated: "10:00",
  topology,
  preflight,
  events: [],
  onNavigate: () => undefined,
  onRefresh: () => undefined,
};

describe("OverviewPage", () => {
  it("shows four decision-focused operational metrics", () => {
    render(<OverviewPage {...baseProps} />);
    for (const label of ["Endpoint Mininet", "OpenFlow inventory", "VLAN 40 · VPWS", "Cảnh báo liên kết"]) expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getAllByText("133/133").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("56 entries").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("l2vpn40")).toBeInTheDocument();
  });

  it("refreshes and navigates to testing, topology and events", () => {
    const navigate = vi.fn();
    const refresh = vi.fn();
    render(<OverviewPage {...baseProps} failedLinks={["core_hq-ce_hq"]} lastError="Agent timeout" onNavigate={navigate} onRefresh={refresh} />);
    fireEvent.click(screen.getByRole("button", { name: "Làm mới" }));
    fireEvent.click(screen.getByRole("button", { name: "Kiểm tra thủ công" }));
    fireEvent.click(screen.getByRole("button", { name: "Mở Topology" }));
    fireEvent.click(screen.getByRole("button", { name: /Agent timeout/ }));
    expect(refresh).toHaveBeenCalledOnce();
    expect(navigate.mock.calls.map((call) => call[0])).toEqual(["testing", "topology", "events"]);
  });

  it("marks VLAN 40 down when the HQ attachment circuit fails", () => {
    render(<OverviewPage {...baseProps} failedLinks={["dist_hq_2-l2vpn_vpws40"]} />);
    expect(screen.getByText("Đường dịch vụ lỗi")).toBeInTheDocument();
  });

  it("does not claim the service is up before topology confirms L2VPN", () => {
    render(<OverviewPage {...baseProps} topology={undefined} />);
    expect(screen.getByText("Chưa xác nhận")).toBeInTheDocument();
    expect(screen.getByText("Chờ preflight")).toBeInTheDocument();
  });

  it("marks the VPWS path as failed when the Branch attachment circuit is down", () => {
    const { container } = render(<OverviewPage {...baseProps} failedLinks={["l2vpn_vpws40-dist_branch"]} />);
    expect(container.querySelector(".overview-l2vpn-path.failed")).toBeInTheDocument();
  });
});
