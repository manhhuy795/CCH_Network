import { fireEvent, render, screen } from "@testing-library/react";
import TopologyCanvas from "./TopologyCanvas";
import type { Topology } from "../api/client";

const switches = ["access_hq_a", "access_hq_b", "access_hq_c", "access_hq_it", "voice_access", "core_hq", "access_branch", "dist_branch"];
const topology: Topology = {
  nodes: [
    { id: "c0", label: "OS-Ken", type: "controller" },
    { id: "project_a", label: "Dự án A", type: "user_group", vlan: 20, count: 1, subnet: "172.16.20.0/24" },
    ...switches.map((id) => ({ id, label: id, type: "switch" })),
  ],
  groups: [{ id: "project_a", label: "Dự án A", type: "user_group", site: "HQ", vlan: 20, count: 1, subnet: "172.16.20.0/24", switch: "access_hq_a", hosts: [{ name: "h20_01", label: "User 1", ip: "172.16.20.11", kind: "user", group: "project_a", group_label: "Dự án A", vlan: 20, site: "HQ" }] }],
  hosts: [],
  links: [{ id: "project_a-access_hq_a", source: "project_a", target: "access_hq_a", type: "access", status: "up" }],
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
  it("draws controller control paths only to eight OVS in technical mode", () => {
    render(<TopologyCanvas {...props} />);
    fireEvent.click(screen.getByText("Kỹ thuật"));
    expect(screen.getAllByTestId("control-path")).toHaveLength(8);
  });

  it("opens node inspector with controller ownership and flow data", () => {
    render(<TopologyCanvas {...props} flows={[{ switch: "access_hq_a", bytes: 128 }]} />);
    fireEvent.click(screen.getByRole("button", { name: "Node access_hq_a" }));
    expect(screen.getByLabelText(/Node · access_hq_a/)).toHaveTextContent("Managed by controller");
    expect(screen.getByLabelText(/Node · access_hq_a/)).toHaveTextContent("128 bytes");
  });

  it("marks backend blocked_at and keeps controller outside decision path", () => {
    render(<TopologyCanvas {...props} decision={{ action: "deny", reason: "policy", path: ["project_a", "access_hq_a", "core_hq"], blocked_at: "core_hq" }} />);
    expect(screen.getByTestId("blocked-at")).toBeInTheDocument();
    expect(screen.getByLabelText("Node OS-Ken").getAttribute("class")).not.toContain("current");
  });

  it("shows link operation lifecycle and impact confirmation", () => {
    const fail = vi.fn();
    render(<TopologyCanvas {...props} onFail={fail} linkOperation={{ linkId: "project_a-access_hq_a", action: "fail", status: "running", message: "Đang ngắt link thật." }} />);
    fireEvent.click(screen.getByLabelText("Link project_a đến access_hq_a"));
    expect(screen.getByLabelText(/Link · project_a/)).toHaveTextContent("Đang thực hiện");
    expect(screen.getByLabelText(/Link · project_a/)).toHaveTextContent("Đang ngắt link thật.");
  });
});
