import { fireEvent, render, screen, within } from "@testing-library/react";
import FlowTable from "./FlowTable";

const flows = [
  { switch: "core_hq", cookie: "0x1001", priority: 400, match: "h101_01 → h103_01", action: "DROP", packets: 9, bytes: 700, source: "h101_01", destination: "h103_01", reason: "Cô lập dự án", raw_match: "ip,nw_src=10.10.101.11", raw_action: "drop" },
  { switch: "infra_access", cookie: "0x1200", priority: 425, match: "h110_01 → h90", action: "ALLOW", packets: 15, bytes: 2400, source: "h110_01", destination: "h90", reason: "Cho phép Voice", raw_match: "ip,nw_dst=10.250.10.10", raw_action: "output:2" },
];

describe("FlowTable", () => {
  it("filters by switch and action", () => {
    render(<FlowTable flows={flows} />);
    fireEvent.change(screen.getByLabelText("Lọc switch"), { target: { value: "core_hq" } });
    const body = screen.getAllByRole("rowgroup")[1];
    expect(within(body).getByText("core_hq")).toBeInTheDocument();
    expect(within(body).queryByText("dist_branch")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Lọc action"), { target: { value: "deny" } });
    expect(within(body).getByText(/DROP/)).toBeInTheDocument();
  });

  it("sorts counters and opens a technical detail drawer", () => {
    render(<FlowTable flows={flows} />);
    fireEvent.click(screen.getByRole("button", { name: /Packets/ }));
    fireEvent.click(screen.getAllByTitle("Xem chi tiết flow")[0]);
    expect(screen.getByLabelText(/Flow ·/)).toHaveTextContent("Match kỹ thuật");
    expect(screen.getByLabelText(/Flow ·/)).toHaveTextContent("Action kỹ thuật");
    expect(screen.getByLabelText(/Flow ·/)).toHaveTextContent("Cho phép Voice");
  });
});
