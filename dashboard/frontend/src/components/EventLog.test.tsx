import { fireEvent, render, screen } from "@testing-library/react";
import type { ActivityEvent, TaskHistoryItem } from "../api/client";
import EventLog from "./EventLog";

const entries: ActivityEvent[] = [
  { id: "1", timestamp: new Date().toISOString(), severity: "info", component: "mininet_control_agent", event_type: "ping", source: "h30_01", destination: "h90", message: "Ping thành công", technical_detail: { rtt: 8 } },
  { id: "2", timestamp: new Date().toISOString(), severity: "error", component: "controller", event_type: "policy", source: "block_social_media", message: "Reload thất bại", error_code: "CONTROLLER_OFFLINE" },
];
const tasks: TaskHistoryItem[] = [{
  task_id: "task-1",
  user_action: "Ping",
  status: "success",
  started_at: new Date().toISOString(),
  ended_at: new Date().toISOString(),
  duration_ms: 42,
  result_summary: "Ping thành công",
  source: "h30_01",
  destination: "h90",
}];

describe("EventLog", () => {
  it("filters structured events by severity, component and pair", () => {
    render(<EventLog entries={entries} tasks={tasks} />);
    fireEvent.change(screen.getByLabelText("Lọc severity"), { target: { value: "error" } });
    expect(screen.getByText("Reload thất bại")).toBeInTheDocument();
    expect(screen.queryByText("Ping thành công", { selector: "article p" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Lọc severity"), { target: { value: "all" } });
    fireEvent.change(screen.getByLabelText("Lọc source destination"), { target: { value: "h30_01" } });
    expect(screen.getByText("h30_01 → h90")).toBeInTheDocument();
  });

  it("shows task history and copies only technical detail", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(<EventLog entries={entries} tasks={tasks} />);
    expect(screen.getByText("task-1")).toBeInTheDocument();
    expect(screen.getByText("42 ms")).toBeInTheDocument();
    fireEvent.click(screen.getAllByTitle("Sao chép chi tiết kỹ thuật")[0]);
    expect(writeText).toHaveBeenCalledWith(JSON.stringify({ rtt: 8 }, null, 2));
  });
});
