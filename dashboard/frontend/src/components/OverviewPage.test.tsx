import { fireEvent, render, screen } from "@testing-library/react";
import OverviewPage from "./OverviewPage";

describe("OverviewPage", () => {
  it("keeps the overview focused on eight operational signals", () => {
    render(
      <OverviewPage
        components={{ controller: { status: "online", message_vi: "Controller sẵn sàng" } }}
        onlineHosts={110}
        totalHosts={115}
        failedLinks={[]}
        lastUpdated="10:00"
        onNavigate={() => undefined}
      />,
    );
    expect(screen.getAllByText(/Controller|Backend|Mininet|Control Agent|Open vSwitch|WebSocket|Host online|Link\/cảnh báo/).length).toBeGreaterThanOrEqual(8);
    expect(screen.getByText("110/115")).toBeInTheDocument();
  });

  it("offers direct navigation to testing, topology and events", () => {
    const navigate = vi.fn();
    render(<OverviewPage components={{}} onlineHosts={0} totalHosts={115} failedLinks={["core_hq-ce_hq"]} lastError="Agent timeout" lastUpdated="" onNavigate={navigate} />);
    fireEvent.click(screen.getByText("Kiểm tra kết nối"));
    fireEvent.click(screen.getByText("Mở Topology"));
    fireEvent.click(screen.getByText("Xem lỗi gần nhất"));
    expect(navigate.mock.calls.map((call) => call[0])).toEqual(["testing", "topology", "events"]);
    expect(screen.getByText("Agent timeout")).toBeInTheDocument();
  });
});
