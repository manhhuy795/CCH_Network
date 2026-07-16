import { act, fireEvent, render, screen } from "@testing-library/react";
import type { Host } from "../api/client";
import RealtimePanel from "./RealtimePanel";

const hosts: Host[] = [
  { name: "h30_01", label: "Project B User 1", ip: "172.10.30.11", kind: "user", group: "project_b", group_label: "Dự án B", vlan: 30, site: "HQ" },
  { name: "h90", label: "Voice", ip: "172.10.90.10", kind: "service", group: "h90", group_label: "Voice", vlan: 90, site: "HQ" },
];

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen?: () => void;
  onclose?: () => void;
  onerror?: () => void;
  onmessage?: (event: MessageEvent) => void;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  close() {
    this.onclose?.();
  }
}

describe("RealtimePanel", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("starts WebSocket monitoring for the selected pair and shows real counters", () => {
    const status = vi.fn();
    render(<RealtimePanel hosts={hosts} source="h30_01" destination="h90" onSource={vi.fn()} onDestination={vi.fn()} onStatus={status} />);
    expect(screen.getByText(/bấm Bắt đầu/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Bắt đầu" }));
    const socket = FakeWebSocket.instances[0];
    expect(socket.url).toContain("source=h30_01");
    act(() => socket.onopen?.());
    act(() => socket.onmessage?.({ data: JSON.stringify({
      timestamp: new Date().toISOString(),
      source: "h30_01",
      destination: "h90",
      ok: true,
      delay_ms: 8,
      packet_loss_percent: 0,
      jitter_ms: 1.2,
      throughput_mbps: 0.4,
      flow_packets: 12,
      flow_bytes: 1200,
      status: "monitoring",
    }) } as MessageEvent));
    expect(screen.getByText("WebSocket online")).toBeInTheDocument();
    expect(screen.getByLabelText(/RTT trung bình: 8 ms/)).toBeInTheDocument();
    expect(screen.getByText(/Flow bytes 1.200/)).toBeInTheDocument();
  });

  it("stops monitoring without starting iperf", () => {
    render(<RealtimePanel hosts={hosts} source="h30_01" destination="h90" onSource={vi.fn()} onDestination={vi.fn()} onStatus={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Bắt đầu" }));
    fireEvent.click(screen.getByRole("button", { name: "Dừng" }));
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Bắt đầu" })).toBeEnabled();
  });

  it("reconnects after an unexpected WebSocket close", () => {
    vi.useFakeTimers();
    render(<RealtimePanel hosts={hosts} source="h30_01" destination="h90" onSource={vi.fn()} onDestination={vi.fn()} onStatus={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Bắt đầu" }));
    act(() => FakeWebSocket.instances[0].onclose?.());
    expect(screen.getByText("WebSocket reconnect lần 1")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1200));
    expect(FakeWebSocket.instances).toHaveLength(2);
    vi.useRealTimers();
  });
});
