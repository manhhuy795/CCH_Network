import { render, screen } from "@testing-library/react";
import type { Firewall } from "../api/client";
import FirewallPanel from "./FirewallPanel";

const firewalls: Firewall[] = [
  {
    name: "fw_hq",
    logical_name: "fw_hq",
    site: "hq",
    inside_interface: "fw_hq-inside",
    outside_interface: "fw_hq-outside",
    nftables_table: "inet cch_filter",
    chain: "forward",
    nftables_status: "unavailable",
    runtime_status: "pending",
    counters: null,
    nat: { configured: false, status: "pending", conclusion: "NAT REQUIREMENT NOT YET CONCLUDED" },
  },
  {
    name: "fw_telesale",
    logical_name: "fw_telesale",
    site: "telesale",
    inside_interface: "fw_telesale-inside",
    outside_interface: "fw_telesale-outside",
    nftables_table: "inet cch_filter",
    chain: "forward",
    nftables_status: "unavailable",
    runtime_status: "pending",
    counters: null,
    nat: { configured: false, status: "pending", conclusion: "NAT REQUIREMENT NOT YET CONCLUDED" },
  },
];

describe("FirewallPanel", () => {
  it("renders both site firewalls and keeps pending runtime explicit", () => {
    render(<FirewallPanel firewalls={firewalls} phase44Runtime={{
      status: "pending",
      message_vi: "Chua co evidence runtime.",
      evidence_available: false,
      nat_conclusion: "NAT REQUIREMENT NOT YET CONCLUDED",
    }} />);

    expect(screen.getByText("fw_hq")).toBeInTheDocument();
    expect(screen.getByText("fw_telesale")).toBeInTheDocument();
    expect(screen.getAllByText("pending").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Chưa có counter runtime/)).toHaveLength(8);
    expect(screen.getAllByText("NAT REQUIREMENT NOT YET CONCLUDED")).toHaveLength(2);
  });
});
