import { fireEvent, render, screen } from "@testing-library/react";
import AppShell from "./AppShell";

const baseProps = {
  page: "overview" as const,
  onPage: vi.fn(),
  overallStatus: "online",
  websocketOnline: false,
  user: { id: "u1", username: "operator", role: "operator" as const },
  authChecking: false,
  onLogout: vi.fn(),
  onHelp: vi.fn(),
};

describe("AppShell", () => {
  it("renders six operational destinations", () => {
    render(<AppShell {...baseProps}>Nội dung</AppShell>);
    for (const label of ["Tổng quan", "Topology", "Kiểm tra kết nối", "Chính sách & OpenFlow", "Hiệu năng", "Sự kiện & nhật ký"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
  });

  it("does not expose an operator token and shows the authenticated role", () => {
    render(<AppShell {...baseProps}>Nội dung</AppShell>);
    expect(screen.queryByLabelText("IT operator token")).not.toBeInTheDocument();
    expect(screen.getByText("Đã đăng nhập · operator")).toBeInTheDocument();
  });

  it("limits viewer navigation to read-only destinations", () => {
    render(<AppShell {...baseProps} user={{ id: "u2", username: "viewer", role: "viewer" }}>Nội dung</AppShell>);
    expect(screen.queryByRole("button", { name: "Kiểm tra kết nối" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sự kiện & nhật ký" })).not.toBeInTheDocument();
  });

  it("changes page from sidebar", () => {
    const onPage = vi.fn();
    render(<AppShell {...baseProps} onPage={onPage}>Nội dung</AppShell>);
    fireEvent.click(screen.getByRole("button", { name: "Topology" }));
    expect(onPage).toHaveBeenCalledWith("topology");
  });
});
