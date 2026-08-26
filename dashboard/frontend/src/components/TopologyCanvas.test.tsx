import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import TopologyCanvas from "./TopologyCanvas";
import type { Topology } from "../api/client";

const switches = ["access_floor1", "access_floor2", "core_hq", "ce_hq1", "ce_hq2", "ce_branch1", "ce_branch2", "dist_branch", "access_branch", "infra_access"];

const topology: Topology = {
  nodes: [
    { id: "c0", label: "OS-Ken SDN Controller", type: "controller" },
    { id: "project_1", label: "Dự án 1", type: "user_group", vlan: 101, count: 10, subnet: "10.10.101.0/24" },
    { id: "project_2", label: "Dự án 2", type: "user_group", vlan: 93, count: 20, subnet: "10.10.93.0/24" },
    { id: "project_3", label: "Dự án 3", type: "user_group", vlan: 103, count: 10, subnet: "10.10.103.0/24" },
    { id: "project_4", label: "Dự án 4", type: "user_group", vlan: 104, count: 10, subnet: "10.10.104.0/24" },
    { id: "fw_hq", label: "Firewall HQ HA", type: "firewall" },
    { id: "fw_telesale", label: "Firewall Branch HA", type: "firewall" },
    { id: "l2vpn_primary", label: "MPLS L2VPN Primary", type: "l2vpn" },
    { id: "l2vpn_backup", label: "MPLS L2VPN Backup", type: "l2vpn" },
    { id: "ipsec_l3", label: "IPsec L3 Tunnel", type: "ipsec" },
    { id: "h90", label: "PBX / Contact Center", type: "service", ip: "10.10.90.10" },
    { id: "hcall", label: "Partner CRM", type: "service", ip: "10.10.90.20" },
    { id: "hdhcp", label: "DHCP Server", type: "infrastructure_service", vlan: 100, ip: "10.10.100.10" },
    ...switches.map((id) => ({ id, label: id, type: "switch" })),
  ],
  groups: [
    {
      id: "project_1",
      label: "Dự án 1",
      type: "user_group",
      site: "hq",
      vlan: 101,
      count: 1,
      subnet: "10.10.101.0/24",
      switch: "access_floor1",
      hosts: [{ name: "h101_01", label: "User 101-01", ip: "10.10.101.11", kind: "user", group: "project_1", group_label: "Dự án 1", vlan: 101, site: "hq" }],
    },
    {
      id: "project_2",
      label: "Dự án 2",
      type: "user_group",
      site: "hq",
      sites: ["hq", "branch"],
      vlan: 93,
      count: 2,
      subnet: "10.10.93.0/24",
      switch: "access_floor1",
      hosts: [
        { name: "h93_01", label: "User 93 HQ", ip: "10.10.93.11", kind: "user", group: "project_2", group_label: "Dự án 2", vlan: 93, site: "hq" },
        { name: "h93_02", label: "User 93 Branch", ip: "10.10.93.12", kind: "user", group: "project_2", group_label: "Dự án 2", vlan: 93, site: "branch" },
      ],
    },
  ],
  hosts: [
    { name: "h101_01", label: "User 101-01", ip: "10.10.101.11", kind: "user", group: "project_1", group_label: "Dự án 1", vlan: 101, site: "hq" },
    { name: "h93_01", label: "User 93 HQ", ip: "10.10.93.11", kind: "user", group: "project_2", group_label: "Dự án 2", vlan: 93, site: "hq" },
    { name: "h93_02", label: "User 93 Branch", ip: "10.10.93.12", kind: "user", group: "project_2", group_label: "Dự án 2", vlan: 93, site: "branch" },
    { name: "h90", label: "PBX / Contact Center", ip: "10.10.90.10", kind: "service", group: "partner", group_label: "Partner", vlan: 90, site: "hq" },
  ],
  links: [
    { id: "project_1-access_floor1", source: "project_1", target: "access_floor1", type: "access", status: "up" },
    { id: "access_floor1-core_hq", source: "access_floor1", target: "core_hq", type: "trunk", status: "up" },
    { id: "core_hq-ce_hq1", source: "core_hq", target: "ce_hq1", type: "l2_handoff", status: "up" },
    { id: "ce_hq1-l2vpn_primary", source: "ce_hq1", target: "l2vpn_primary", type: "l2vpn", status: "up" },
    { id: "l2vpn_primary-ce_branch1", source: "l2vpn_primary", target: "ce_branch1", type: "l2vpn", status: "up" },
    { id: "ce_branch1-dist_branch", source: "ce_branch1", target: "dist_branch", type: "l2_handoff", status: "up" },
    { id: "dist_branch-access_branch", source: "dist_branch", target: "access_branch", type: "trunk", status: "up" },
    { id: "access_branch-project_2", source: "access_branch", target: "project_2", type: "access", status: "up" },
    { id: "core_hq-fw_hq", source: "core_hq", target: "fw_hq", type: "routed", status: "up" },
    { id: "fw_hq-ipsec_l3", source: "fw_hq", target: "ipsec_l3", type: "ipsec", status: "up" },
    { id: "ipsec_l3-fw_telesale", source: "ipsec_l3", target: "fw_telesale", type: "ipsec", status: "up" },
  ],
  policy_map: {},
  summary: { user_count: 50, service_count: 5, controlled_ovs_count: 8 },
};

const defaultProps = {
  topology,
  links: topology.links,
  activeIndex: 0,
  failedLinks: [] as string[],
  liveLinkControl: true,
  authenticated: true,
  source: "h101_01",
  destination: "h93_02",
  onFail: vi.fn(),
  onRecover: vi.fn(),
  onSource: vi.fn(),
  onDestination: vi.fn(),
};

describe("TopologyCanvas (Enterprise v7)", () => {
  it("renders Enterprise v7 title without the simulation note", () => {
    render(<TopologyCanvas {...defaultProps} />);
    expect(screen.getByText(/Sơ đồ logic mạng doanh nghiệp · v7/)).toBeInTheDocument();
    expect(screen.queryByText(/Simulation Honesty/)).not.toBeInTheDocument();
    expect(screen.getByTestId("topology-canvas")).toHaveClass("fixed-layout");
  });

  it("does not highlight source or destination before the operator chooses them", () => {
    render(<TopologyCanvas {...defaultProps} source="" destination="" />);
    expect(screen.queryByText("NGUỒN")).not.toBeInTheDocument();
    expect(screen.queryByText("ĐÍCH")).not.toBeInTheDocument();
  });

  it("renders Enterprise v7 interactive topology architecture underlay and quick search", () => {
    render(<TopologyCanvas {...defaultProps} />);
    expect(screen.getByRole("img", { name: /Enterprise v7 Architecture/ })).toBeInTheDocument();
    expect(screen.queryByText(/DỰ PHÒNG WAN/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Chỉ mở rộng Layer 2/)).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Tìm kiếm thiết bị" })).toBeInTheDocument();
  });

  it("keeps the architecture fixed and provides fullscreen access", () => {
    render(<TopologyCanvas {...defaultProps} />);
    expect(screen.queryByRole("button", { name: "Phóng to" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Toàn màn hình" })).toBeInTheDocument();
  });

  it("renders separate VLAN 93 presentation nodes for HQ and Branch", () => {
    render(<TopologyCanvas {...defaultProps} />);
    expect(screen.getByRole("button", { name: "Node Dự án 2 · HQ" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Node Dự án 2 · Branch" })).toBeInTheDocument();
  });

  it("opens node inspector drawer and displays device details", () => {
    render(<TopologyCanvas {...defaultProps} flows={[{ switch: "core_hq", bytes: 512 }]} />);
    fireEvent.click(screen.getByRole("button", { name: "Node core_hq" }));

    expect(screen.getByRole("complementary", { name: /Chi tiết Node · core_hq/ })).toBeInTheDocument();
    expect(screen.getAllByText("Collapsed Core/Distribution HA (HQ)").length).toBeGreaterThanOrEqual(1);
  });

  it("allows selecting source and destination endpoints from node click", () => {
    const onSource = vi.fn();
    const onDestination = vi.fn();
    const { rerender } = render(<TopologyCanvas {...defaultProps} source="" destination="" onSource={onSource} onDestination={onDestination} />);

    const project1Node = screen.getByRole("button", { name: "Node Dự án 1" });
    fireEvent.click(project1Node);
    expect(onSource).toHaveBeenCalledWith("h101_01");
    expect(screen.queryByRole("complementary", { name: /Chi tiết Node/ })).not.toBeInTheDocument();

    rerender(<TopologyCanvas {...defaultProps} source="h101_01" destination="" onSource={onSource} onDestination={onDestination} />);
    fireEvent.click(screen.getByRole("button", { name: "Node Dự án 2 · HQ" }));
    expect(onDestination).toHaveBeenCalledWith("h93_01");

    rerender(<TopologyCanvas {...defaultProps} source="h101_01" destination="h93_01" onSource={onSource} onDestination={onDestination} />);
    fireEvent.click(screen.getByRole("button", { name: "Node Dự án 1" }));
    expect(onSource).toHaveBeenLastCalledWith("");
    rerender(<TopologyCanvas {...defaultProps} source="" destination="h93_01" onSource={onSource} onDestination={onDestination} />);
    fireEvent.click(screen.getByRole("button", { name: "Node PBX / Contact Center" }));
    expect(onSource).toHaveBeenLastCalledWith("h90");

    rerender(<TopologyCanvas {...defaultProps} source="h101_01" destination="h93_01" onSource={onSource} onDestination={onDestination} />);
    fireEvent.click(screen.getByRole("button", { name: "Node Dự án 2 · HQ" }));
    expect(onDestination).toHaveBeenLastCalledWith("");
  });

  it("marks blocked_at with animated deny marker and stops path animation at blocked node", () => {
    render(
      <TopologyCanvas
        {...defaultProps}
        decision={{
          action: "deny",
          reason: "Firewall intersite policy blocked",
          path: ["project_1", "access_floor1", "core_hq", "fw_hq"],
          blocked_at: "fw_hq",
        }}
        activeIndex={3}
      />
    );
    expect(screen.getByTestId("blocked-at")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Node (fw_hq|Firewall HQ HA)/ }).getAttribute("class")).toContain("current");
  });

  it("provides L2VPN Primary path fail and recover buttons", () => {
    const onFail = vi.fn();
    const onRecover = vi.fn();
    render(<TopologyCanvas {...defaultProps} onFail={onFail} onRecover={onRecover} failedLinks={["ce_hq1-l2vpn_primary"]} />);

    // Fail button on the UP link
    const failBtn = screen.getByRole("button", { name: /Ngắt thử nghiệm Primary · l2vpn_primary ↔ ce_branch1/ });
    expect(failBtn).toHaveTextContent("Ngắt liên kết");
    fireEvent.click(failBtn);
    expect(onFail).toHaveBeenCalledWith("l2vpn_primary-ce_branch1");

    // Recover button on the DOWN link
    const recoverBtn = screen.getByRole("button", { name: /Khôi phục Primary · ce_hq1 ↔ l2vpn_primary/ });
    expect(recoverBtn).toHaveTextContent("Khôi phục liên kết");
    fireEvent.click(recoverBtn);
    expect(onRecover).toHaveBeenCalledWith("ce_hq1-l2vpn_primary");
  });

  it("filters nodes when typing into search input", () => {
    render(<TopologyCanvas {...defaultProps} />);
    const searchInput = screen.getByRole("textbox", { name: "Tìm kiếm thiết bị" });
    fireEvent.change(searchInput, { target: { value: "core_hq" } });

    const coreNode = screen.getByRole("button", { name: "Node core_hq" });
    expect(coreNode.getAttribute("class")).not.toContain("dimmed");

    const branchAccess = screen.getByRole("button", { name: "Node access_branch" });
    expect(branchAccess.getAttribute("class")).toContain("dimmed");
  });

  it("renders Enterprise v7 legend explaining VLAN 93, MPLS, IPsec, and Partner zones", () => {
    render(<TopologyCanvas {...defaultProps} />);
    const legend = screen.getByLabelText("Chú thích sơ đồ mạng v7");
    expect(legend).toHaveTextContent("VLAN 93");
    expect(legend).toHaveTextContent("MPLS L2VPN");
    expect(legend).toHaveTextContent("IPsec L3");
    expect(legend).toHaveTextContent("Partner PBX/CRM");
  });
});
