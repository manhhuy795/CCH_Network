import { fireEvent, render, screen } from "@testing-library/react";
import { mockFlows, mockPolicies, mockTopology } from "./api/mockData";

const apiMock = vi.hoisted(() => ({
  activity: vi.fn(),
  authStatus: vi.fn(),
  flows: vi.fn(),
  login: vi.fn(),
  me: vi.fn(),
  policies: vi.fn(),
  status: vi.fn(),
  topology: vi.fn(),
}));

vi.mock("./api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api/client")>();
  return { ...actual, api: apiMock };
});

import App from "./App";

describe("App authentication navigation", () => {
  it("opens Overview after login and exposes SDN as a dedicated page", async () => {
    const user = { id: "u1", username: "admin", role: "admin" as const };
    apiMock.me.mockRejectedValueOnce(new Error("No session"));
    apiMock.login.mockResolvedValueOnce({ user });
    apiMock.topology.mockResolvedValue(mockTopology);
    apiMock.policies.mockResolvedValue(mockPolicies);
    apiMock.flows.mockResolvedValue({ flows: mockFlows });
    apiMock.status.mockResolvedValue({
      status: "online",
      components: {
        backend: { status: "online" },
        controller: { status: "online" },
        mininet_topology: { status: "online" },
        mininet_control_agent: { status: "online" },
        openvswitch: { status: "online" },
      },
      hosts: {},
    });
    apiMock.authStatus.mockResolvedValue({ session_ttl_seconds: 3600, csrf_header: "X-CSRF-Token" });
    apiMock.activity.mockResolvedValue({ events: [], tasks: [] });

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Đăng nhập" }));

    expect(await screen.findByRole("heading", { name: "Tổng quan hệ thống" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "SDN & OpenFlow" }));
    expect(await screen.findByRole("heading", { name: "Bảng luồng OpenFlow" })).toBeInTheDocument();
  });
});
