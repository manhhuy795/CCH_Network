import { fireEvent, render, screen } from "@testing-library/react";
import type { DashboardPreflight, Topology } from "../api/client";
import OverviewPage from "./OverviewPage";

const topology = {
  nodes: [], groups: [], hosts: [], links: [
    { id: "core_hq-ce_hq1", source: "core_hq", target: "ce_hq1", type: "l2vpn", status: "up" },
    { id: "ce_hq1-l2vpn_primary", source: "ce_hq1", target: "l2vpn_primary", type: "l2vpn", status: "up" },
    { id: "l2vpn_primary-ce_branch1", source: "l2vpn_primary", target: "ce_branch1", type: "l2vpn", status: "up" },
    { id: "ce_branch1-dist_branch", source: "ce_branch1", target: "dist_branch", type: "l2vpn", status: "up" },
  ], policy_map: {},
  l2vpn: { customer_vlan: 93, runtime_bridge: "l2vpn_primary", type: "VPWS / E-Line logic" },
  summary: { user_count: 90, service_count: 5, controlled_ovs_count: 6, l2vpn_service_count: 1 },
} satisfies Topology;

const preflight = {
  status: "passed",
  available: true,
  age_seconds: 12,
  stale: false,
  source: "Mininet Control Agent + ovs-ofctl OpenFlow13",
  summary: {
    checks_passed: 5, checks_total: 5, endpoints_online: 111, endpoints_total: 111,
    user_hosts_online: 90, switches_ready: 6, switches_expected: 6, flow_entries: 56,
  },
  cases: [
    { id: "vlan93_hq_to_branch", label: "VLAN 93 · HQ → Branch", source: "h93_01", destination: "h93_11", expectation: "allow", observed: "reachable", evidence: "L2VPN Primary", passed: true, avg_rtt_ms: 0.14, packet_loss_percent: 0 },
    { id: "vlan93_branch_to_hq", label: "VLAN 93 · Branch → HQ", source: "h93_11", destination: "h93_01", expectation: "allow", observed: "reachable", evidence: "L2VPN return", passed: true, avg_rtt_ms: 0.16, packet_loss_percent: 0 },
    { id: "project_voice_to_pbx", label: "Project 1 → PBX", source: "h101_01", destination: "h90", expectation: "allow", observed: "reachable", evidence: "Voice policy", passed: true, avg_rtt_ms: 0.2, packet_loss_percent: 0 },
    { id: "project_segmentation", label: "Project 1 ↛ Project 3", source: "h101_01", destination: "h103_01", expectation: "deny", observed: "blocked", evidence: "Isolation", passed: true, packet_loss_percent: 100 },
    { id: "guest_isolation", label: "Guest ↛ Project 2", source: "guest_01", destination: "h93_01", expectation: "deny", observed: "blocked", evidence: "Guest isolation", passed: true, packet_loss_percent: 100 },
  ],
} satisfies DashboardPreflight;

const baseProps = {
  components: { controller: { status: "online", message_vi: "Controller sẵn sàng" } },
  onlineHosts: 111,
  totalHosts: 111,
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
    for (const label of ["Endpoint Mininet", "OpenFlow inventory", "VLAN 93 · L2VPN", "Cảnh báo liên kết"]) expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getAllByText("111/111").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("56 entries").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("l2vpn_primary")).toBeInTheDocument();
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

  it("marks VLAN 93 down when the HQ attachment circuit fails", () => {
    render(<OverviewPage {...baseProps} failedLinks={["core_hq-ce_hq1"]} />);
    expect(screen.getByText("Đường dịch vụ lỗi")).toBeInTheDocument();
  });

  it("does not claim the service is up before topology confirms L2VPN", () => {
    render(<OverviewPage {...baseProps} topology={undefined} />);
    expect(screen.getByText("Chưa xác nhận")).toBeInTheDocument();
    expect(screen.getByText("Chờ preflight")).toBeInTheDocument();
  });

  it("marks the VPWS path as failed when the Branch attachment circuit is down", () => {
    const { container } = render(<OverviewPage {...baseProps} failedLinks={["l2vpn_primary-ce_branch1"]} />);
    expect(container.querySelector(".overview-l2vpn-path.failed")).toBeInTheDocument();
  });
});
