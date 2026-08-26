import { fireEvent, render, screen } from "@testing-library/react";
import AppShell from "./AppShell";

const baseProps = {
  page: "overview" as const,
  onPage: vi.fn(),
  overallStatus: "online",
  websocketState: "idle" as const,
  user: { id: "u1", username: "operator", role: "operator" as const },
  authChecking: false,
  onLogout: vi.fn(),
  onHelp: vi.fn(),
};

describe("AppShell", () => {
  it("renders dedicated policy and SDN destinations (with testing merged into topology)", () => {
    render(<AppShell {...baseProps}>Nội dung</AppShell>);
    for (const label of ["Tổng quan", "Topology", "Chính sách bảo mật", "SDN & OpenFlow", "Hiệu năng", "Sự kiện & nhật ký"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("button", { name: "Kiểm tra kết nối" })).not.toBeInTheDocument();
  });

  it("does not expose an operator token and shows the authenticated role", () => {
    render(<AppShell {...baseProps}>Nội dung</AppShell>);
    expect(screen.queryByLabelText("IT operator token")).not.toBeInTheDocument();
    expect(screen.getByText("Đã đăng nhập · operator")).toBeInTheDocument();
  });

  it("limits viewer navigation to read-only destinations", () => {
    render(<AppShell {...baseProps} user={{ id: "u2", username: "viewer", role: "viewer" }}>Nội dung</AppShell>);
    expect(screen.queryByRole("button", { name: "Sự kiện & nhật ký" })).not.toBeInTheDocument();
  });

  it("changes page from sidebar", () => {
    const onPage = vi.fn();
    render(<AppShell {...baseProps} onPage={onPage}>Nội dung</AppShell>);
    fireEvent.click(screen.getByRole("button", { name: "Topology" }));
    expect(onPage).toHaveBeenCalledWith("topology");
    fireEvent.click(screen.getByRole("button", { name: "SDN & OpenFlow" }));
    expect(onPage).toHaveBeenCalledWith("sdn");
  });

  it("persists the selected color mode", () => {
    localStorage.removeItem("cch-theme");
    render(<AppShell {...baseProps}>Nội dung</AppShell>);
    fireEvent.click(screen.getByRole("button", { name: "Tối" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("cch-theme")).toBe("dark");
  });
});
