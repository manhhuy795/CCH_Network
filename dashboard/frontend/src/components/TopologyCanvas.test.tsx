import { fireEvent, render, screen } from "@testing-library/react";
import TopologyCanvas from "./TopologyCanvas";
import type { Topology } from "../api/client";

const switches = ["access_floor1", "access_floor2", "dist_hq_1", "dist_hq_2", "core_hq", "access_branch", "dist_branch", "infra_access"];
const topology: Topology = {
  nodes: [
    { id: "c0", label: "OS-Ken", type: "controller" },
    { id: "project_a", label: "Dự án A", type: "user_group", vlan: 20, count: 1, subnet: "172.16.20.0/24" },
    ...switches.map((id) => ({ id, label: id, type: "switch" })),
  ],
  groups: [{ id: "project_a", label: "Dự án A", type: "user_group", site: "HQ", vlan: 20, count: 1, subnet: "172.16.20.0/24", switch: "access_floor1", hosts: [{ name: "h20_01", label: "User 1", ip: "172.16.20.11", kind: "user", group: "project_a", group_label: "Dự án A", vlan: 20, site: "HQ" }] }],
  hosts: [],
  links: [{ id: "project_a-access_floor1", source: "project_a", target: "access_floor1", type: "access", status: "up" }],
  topology_contract: {
    source_of_truth: ["vars/network_model.yml", "vars/routing.yml", "vars/firewall_policies.yml"],
    runtime_authority: "Mininet Control Agent and live OVS/nftables evidence",
    design_only_is_runtime: false,
    provider_domain: {
      label: "ISP / Carrier Cloud",
      handoff_layer: "WAN Handoff Layer",
      mode: "logical_provider_demarcation",
      circuits: {
        primary: { id: "isp_circuit_a", label: "ISP Circuit A - Primary", state: "active", color: "blue", sites: ["hq", "branch_telesale"] },
        backup: { id: "isp_circuit_b", label: "ISP Circuit B - Backup", state: "standby", color: "purple", sites: ["hq", "branch_telesale"] },
      },
    },
    provider_handoff_paths: {
      primary: { provider_id: "isp_circuit_a", handoff_id: "wan_handoff_primary", label: "Carrier A - HQ + Branch", state: "active", color: "blue", site_firewalls: { hq: { firewall: "fw_hq", runtime_link: "fw_hq_to_internet_zone" } } },
      backup: { provider_id: "isp_circuit_b", handoff_id: "wan_handoff_backup", label: "Carrier B - HQ + Branch", state: "standby", color: "purple", site_firewalls: { hq: { firewall: "fw_hq", runtime_link: "fw_hq_to_internet_zone" } } },
    },
    firewall_redundancy: {
      hq: { runtime_node: "fw_hq", design_role: "ha_pair", inside_node: "core_hq", outside_circuits: ["primary", "backup"], runtime_state: "runtime_namespace", representation: "design_metadata", policy_site: "hq", design_members: ["fw_hq_primary", "fw_hq_backup"], runtime_interfaces: { inside: "fw_hq-eth0", outside: "fw_hq-eth1" } },
    },
    server_zone: {
      runtime_switch: "infra_access",
      components: {
        sbc_voice_edge: { runtime_node: "h90", design_role: "dmz_sbc", runtime_state: "collapsed_voice_placeholder" },
        database_server: { runtime_node: null, runtime_state: "design_only_not_simulated" },
      },
      notes: {},
    },
    design_nodes: [{ id: "isp_circuit_a", logical_name: "isp_circuit_a", label: "ISP Circuit A - Primary", type: "provider_circuit", role: "primary", site: "wan", runtime_node: null, runtime_state: "design_only", representation: "design_only", controller_managed: false, status: "design_only", status_source: "source_of_truth", runtime_bridge: null }],
  },
  design_nodes: [{ id: "isp_circuit_a", logical_name: "isp_circuit_a", label: "ISP Circuit A - Primary", type: "provider_circuit", role: "primary", site: "wan", runtime_node: null, runtime_state: "design_only", representation: "design_only", controller_managed: false, status: "design_only", status_source: "source_of_truth", runtime_bridge: null }],
  policy_map: {},
  summary: { user_count: 1, service_count: 0, controlled_ovs_count: 8 },
};

const props = {
  topology,
  links: topology.links,
  activeIndex: 0,
  failedLinks: [] as string[],
  liveLinkControl: true,
  authenticated: true,
  source: "h20_01",
  onFail: vi.fn(),
  onRecover: vi.fn(),
  onSource: vi.fn(),
  onDestination: vi.fn(),
};

describe("TopologyCanvas", () => {
  it("draws controller control paths only to nine OVS in technical mode", () => {
    render(<TopologyCanvas {...props} />);
    fireEvent.click(screen.getByText("Kỹ thuật"));
    expect(screen.getAllByTestId("control-path")).toHaveLength(8);
  });

  it("opens node inspector with controller ownership and flow data", () => {
    render(<TopologyCanvas {...props} flows={[{ switch: "access_floor1", bytes: 128 }]} />);
    fireEvent.click(screen.getByRole("button", { name: "Node access_floor1" }));
    expect(screen.getByLabelText(/Node · access_floor1/)).toHaveTextContent("Managed by controller");
    expect(screen.getByLabelText(/Node · access_floor1/)).toHaveTextContent("128 bytes");
  });

  it("marks backend blocked_at and keeps controller outside decision path", () => {
    render(<TopologyCanvas {...props} decision={{ action: "deny", reason: "policy", path: ["project_a", "access_floor1", "core_hq"], blocked_at: "core_hq" }} />);
    expect(screen.getByTestId("blocked-at")).toBeInTheDocument();
    expect(screen.getByLabelText("Node OS-Ken").getAttribute("class")).not.toContain("current");
  });

  it("shows link operation lifecycle and impact confirmation", () => {
    const fail = vi.fn();
    render(<TopologyCanvas {...props} onFail={fail} linkOperation={{ linkId: "project_a-access_floor1", action: "fail", status: "running", message: "Đang ngắt link thật." }} />);
    fireEvent.click(screen.getByLabelText("Link project_a đến access_floor1"));
    expect(screen.getByLabelText(/Link · project_a/)).toHaveTextContent("Đang thực hiện");
    expect(screen.getByLabelText(/Link · project_a/)).toHaveTextContent("Đang ngắt link thật.");
  });

  it("opens a link inspector with keyboard activation", () => {
    render(<TopologyCanvas {...props} />);
    fireEvent.keyDown(screen.getByRole("button", { name: "Link project_a đến access_floor1" }), { key: "Enter" });
    expect(screen.getByLabelText(/Link · project_a/)).toBeInTheDocument();
  });
  it("renders source-truth design metadata separately from runtime topology", () => {
    render(<TopologyCanvas {...props} />);
    const contract = screen.getByTestId("topology-design-contract");
    expect(contract).toHaveTextContent("Design-only");
    expect(contract).toHaveTextContent("ISP Circuit A - Primary");
    expect(contract).toHaveTextContent("ISP Circuit B - Backup");
    expect(contract).toHaveTextContent("fw_hq_primary");
    expect(screen.getByTestId("design-server-zone-list")).toHaveTextContent("Database Server");
    expect(screen.queryByRole("button", { name: "Node ISP Circuit A - Primary" })).not.toBeInTheDocument();
    expect(screen.queryAllByTestId("control-path")).toHaveLength(0);
  });
});
