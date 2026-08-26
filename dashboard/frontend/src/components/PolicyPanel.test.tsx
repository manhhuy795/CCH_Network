import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { PolicyPayload } from "../api/client";
import PolicyPanel from "./PolicyPanel";

const payload: PolicyPayload = {
  policies: { block_social_media: true },
  inventory: [{
    key: "block_social_media",
    name: "Chặn Social Media",
    description: "Chặn mạng xã hội cho user nghiệp vụ.",
    source: "Managed user VLAN",
    destination: "hsocial",
    action: "DROP",
    enforcement_point: "fw_hq / fw_telesale",
    priority: 0,
    cookie: "n/a",
    enforcement_engine: "nftables",
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
    expect(screen.getByText("fw_hq / fw_telesale")).toBeInTheDocument();
    expect(screen.getByText("n/a")).toBeInTheDocument();
    expect(screen.getByText("Stateful nftables")).toBeInTheDocument();
    expect(screen.queryByText(/5 ms/)).not.toBeInTheDocument();
  });

  it("requires confirmation with impact summary before toggling", async () => {
    const toggle = vi.fn().mockResolvedValue(undefined);
    render(<PolicyPanel policies={payload} onToggle={toggle} />);
    fireEvent.click(screen.getByRole("button", { name: "Tắt policy" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("fw_hq / fw_telesale");
    expect(screen.getByRole("dialog")).toHaveTextContent("inet cch_filter");
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
