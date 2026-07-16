import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import type { Host, TestResult, Topology } from "../api/client";
import TestPanel from "./TestPanel";
import type { NetworkTestType } from "./testWorkflow";

const hosts: Host[] = [
  { name: "h20_01", label: "Dự án A - User 1", ip: "172.10.20.11", kind: "user", group: "project_a", group_label: "Dự án A", vlan: 20, site: "HQ" },
  { name: "h30_01", label: "Dự án B - User 1", ip: "172.10.30.11", kind: "user", group: "project_b", group_label: "Dự án B", vlan: 30, site: "HQ" },
  { name: "h90", label: "Voice service", ip: "172.10.90.10", kind: "service", group: "h90", group_label: "Voice", vlan: 90, site: "HQ" },
];

const policyMap: Topology["policy_map"] = {
  project_a: {
    title: "Project A",
    allow: ["h90"],
    deny: ["project_b"],
    notes: { h90: "Được phép dùng Voice", project_b: "Cô lập dự án" },
  },
};

function baseProps(overrides: Partial<React.ComponentProps<typeof TestPanel>> = {}): React.ComponentProps<typeof TestPanel> {
  return {
    hosts,
    policyMap,
    source: "h20_01",
    destination: "h90",
    seconds: 5,
    testType: "ping",
    resultType: "ping",
    busy: false,
    elapsedSeconds: 0,
    websocketOnline: true,
    onSource: vi.fn(),
    onDestination: vi.fn(),
    onSeconds: vi.fn(),
    onTestType: vi.fn(),
    onRun: vi.fn(),
    onCancel: vi.fn(),
    ...overrides,
  };
}

describe("TestPanel", () => {
  it("renders a successful real Ping result and backend path", () => {
    const result: TestResult = {
      ok: true,
      message: "Ping thành công",
      result: { packet_loss_percent: 0, rtt_avg_ms: 12.4 },
      decision: {
        action: "allow",
        reason: "Voice được cho phép",
        path: ["project_a", "access_hq_a", "core_hq", "voice_access", "h90"],
        enforcement_switch: "core_hq",
      },
    };
    render(<TestPanel {...baseProps({ result })} />);
    expect(screen.getByText("Ping thành công")).toBeInTheDocument();
    expect(screen.getByText("12.4 ms")).toBeInTheDocument();
    expect(screen.getByText(/project_a → access_hq_a → core_hq/)).toBeInTheDocument();
    expect(screen.getByText("core_hq")).toBeInTheDocument();
  });

  it("shows progress and locks configuration while a task is running", () => {
    render(<TestPanel {...baseProps({ busy: true, elapsedSeconds: 3, testType: "udp" })} />);
    expect(screen.getByText("Đang chạy UDP Jitter")).toBeInTheDocument();
    expect(screen.getByText("3s")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Chạy UDP Jitter/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Ping" })).toBeDisabled();
    expect(screen.getByLabelText("Nguồn endpoint")).toBeDisabled();
    expect(screen.getByRole("button", { name: /Dự án A/ })).toBeDisabled();
  });

  it("reports a disconnected realtime channel without blocking HTTP tests", () => {
    render(<TestPanel {...baseProps({ websocketOnline: false })} />);
    const warning = screen.getByText("WebSocket mất kết nối").closest("[role='status']");
    expect(warning).toHaveTextContent("WebSocket mất kết nối");
    expect(warning).toHaveTextContent("API HTTP");
    expect(screen.getByRole("button", { name: /Chạy Ping/ })).toBeEnabled();
  });

  it.each([
    ["AGENT_TIMEOUT", "Agent vẫn có thể đang xử lý"],
    ["BACKEND_OFFLINE", "FastAPI backend không phản hồi"],
    ["IPERF_BUSY", "Đích đang có phiên iperf khác"],
    ["POLICY_DENIED", "Policy đang chặn luồng này"],
  ])("renders %s with operator guidance", (errorCode, guidance) => {
    render(<TestPanel {...baseProps({
      result: { ok: false, message: "Không thể hoàn tất phép đo", error_code: errorCode },
    })} />);
    expect(screen.getByRole("alert")).toHaveTextContent(errorCode);
    expect(screen.getByRole("alert")).toHaveTextContent(guidance);
  });

  it("renders UDP, TCP and voice fields from the completed result type", () => {
    const { rerender } = render(<TestPanel {...baseProps({
      testType: "ping",
      resultType: "udp",
      result: {
        ok: true,
        message: "UDP hoàn tất",
        duration: 5,
        session_id: "udp-1",
        result: { throughput_mbps: 8.4, jitter_ms: 2.1, packet_loss_percent: 0.5, lost_packets: 1, total_datagrams: 200 },
      },
    })} />);
    expect(screen.getByText("8.4 Mbps")).toBeInTheDocument();
    expect(screen.getByText("1/200")).toBeInTheDocument();

    rerender(<TestPanel {...baseProps({
      resultType: "tcp",
      result: { ok: true, message: "TCP hoàn tất", duration: 5, session_id: "tcp-1", result: { throughput_mbps: 94, transferred_bytes: 58750000 } },
    })} />);
    expect(screen.getByText("58750000 bytes")).toBeInTheDocument();

    rerender(<TestPanel {...baseProps({
      resultType: "quality",
      result: { ok: true, message: "Voice hoàn tất", result: { rtt_avg_ms: 35, jitter_ms: 3, packet_loss_percent: 0, mos: 4.3, r_factor: 91, rating: "Tốt" } },
    })} />);
    expect(screen.getByText("4.3")).toBeInTheDocument();
    expect(screen.getByText(/không phải cuộc gọi SIP\/RTP thật/)).toBeInTheDocument();
  });

  it("retries the completed test type even if another selector is active", () => {
    const onRun = vi.fn();
    render(<TestPanel {...baseProps({
      testType: "ping",
      resultType: "udp",
      result: { ok: false, message: "UDP timeout", error_code: "AGENT_TIMEOUT" },
      onRun,
    })} />);
    fireEvent.click(screen.getByRole("button", { name: "Chạy lại" }));
    expect(onRun).toHaveBeenCalledTimes(1);
    expect(onRun).toHaveBeenCalledWith("udp");
  });

  it("prevents source and destination from being identical", () => {
    render(<TestPanel {...baseProps({ source: "h20_01", destination: "h20_01" })} />);
    expect(screen.getByText("Nguồn và đích phải khác nhau.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Chạy Ping/ })).toBeDisabled();
  });

  it("does not start a second session on a rapid double click", () => {
    const onRun = vi.fn();
    function Harness() {
      const [busy, setBusy] = useState(false);
      const run = (action: NetworkTestType | "simulate" | "block" | "unblock") => {
        onRun(action);
        setBusy(true);
      };
      return <TestPanel {...baseProps({ busy, onRun: run })} />;
    }
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: /Chạy Ping/ }));
    fireEvent.click(screen.getByRole("button", { name: /Chạy Ping/ }));
    expect(onRun).toHaveBeenCalledTimes(1);
  });
});
