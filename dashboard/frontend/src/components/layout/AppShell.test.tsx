import { fireEvent, render, screen } from "@testing-library/react";
import AppShell from "./AppShell";

const baseProps = {
  page: "overview" as const,
  onPage: vi.fn(),
  overallStatus: "online",
  websocketOnline: false,
  authenticated: false,
  authChecking: false,
  token: "",
  onToken: vi.fn(),
  onAuthenticate: vi.fn(),
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

  it("hides token input after authentication", () => {
    const { rerender } = render(<AppShell {...baseProps} token="secret">Nội dung</AppShell>);
    expect(screen.getByLabelText("IT operator token")).toBeInTheDocument();
    rerender(<AppShell {...baseProps} authenticated token="">Nội dung</AppShell>);
    expect(screen.queryByLabelText("IT operator token")).not.toBeInTheDocument();
    expect(screen.getByText("Đã xác thực")).toBeInTheDocument();
  });

  it("changes page from sidebar", () => {
    const onPage = vi.fn();
    render(<AppShell {...baseProps} onPage={onPage}>Nội dung</AppShell>);
    fireEvent.click(screen.getByRole("button", { name: "Topology" }));
    expect(onPage).toHaveBeenCalledWith("topology");
  });
});
