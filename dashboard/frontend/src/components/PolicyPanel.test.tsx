import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { PolicyPayload } from "../api/client";
import PolicyPanel from "./PolicyPanel";

const payload: PolicyPayload = {
  policies: { block_social_media: true },
  inventory: [{
    key: "block_social_media",
    name: "Chặn Social Media",
    description: "Chặn mạng xã hội cho user nghiệp vụ.",
    source: "VLAN 20 / 30 / 40",
    destination: "hsocial",
    action: "DROP",
    enforcement_point: "core_hq",
    priority: 470,
    cookie: "0x1304",
    enabled: true,
    configuration_status: "Enabled",
    lifecycle_status: "Applied",
    controller_acknowledged: true,
    updated_at: "2026-07-16T10:00:00Z",
  }],
};

describe("PolicyPanel", () => {
  it("shows configured and controller-applied state separately", () => {
    render(<PolicyPanel policies={payload} />);
    expect(screen.getByText("Enabled")).toBeInTheDocument();
    expect(screen.getByText("Applied")).toBeInTheDocument();
    expect(screen.getByText("Đã xác nhận")).toBeInTheDocument();
    expect(screen.getByText("core_hq")).toBeInTheDocument();
    expect(screen.getByText("0x1304")).toBeInTheDocument();
  });

  it("requires confirmation with impact summary before toggling", async () => {
    const toggle = vi.fn().mockResolvedValue(undefined);
    render(<PolicyPanel policies={payload} onToggle={toggle} />);
    fireEvent.click(screen.getByRole("button", { name: "Tắt policy" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("core_hq");
    expect(screen.getByRole("dialog")).toHaveTextContent("0x1304");
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Tắt policy" }));
    await waitFor(() => expect(toggle).toHaveBeenCalledWith("block_social_media", false));
  });

  it("does not present an unacknowledged policy as Applied", () => {
    render(<PolicyPanel policies={{
      ...payload,
      inventory: [{ ...payload.inventory[0], lifecycle_status: "Out of sync", controller_acknowledged: false }],
    }} />);
    expect(screen.getByText("Out of sync")).toBeInTheDocument();
    expect(screen.getByText("Chưa xác nhận")).toBeInTheDocument();
  });
});
