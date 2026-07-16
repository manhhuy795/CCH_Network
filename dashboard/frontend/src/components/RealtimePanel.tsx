import { Pause, Play } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Host, RealtimeMetric } from "../api/client";
import { wsUrl } from "../api/client";
import StatusBadge from "./ui/StatusBadge";

type Props = {
  hosts: Host[];
  source: string;
  destination: string;
  onSource: (value: string) => void;
  onDestination: (value: string) => void;
  onStatus: (connected: boolean) => void;
};

const chartFields: Array<{ field: keyof RealtimeMetric; label: string; unit: string }> = [
  { field: "throughput_mbps", label: "Throughput theo flow counter", unit: "Mbps" },
  { field: "delay_ms", label: "RTT trung bình", unit: "ms" },
  { field: "jitter_ms", label: "Jitter", unit: "ms" },
  { field: "packet_loss_percent", label: "Packet loss", unit: "%" },
  { field: "flow_packets", label: "Flow packets", unit: "packets" },
];

function Sparkline({ data, field, label, unit }: { data: RealtimeMetric[]; field: keyof RealtimeMetric; label: string; unit: string }) {
  const values = data.map((item) => Number(item[field] ?? 0));
  const max = Math.max(1, ...values);
  const points = values.map((value, index) => {
    const x = data.length <= 1 ? 0 : (index / (data.length - 1)) * 240;
    const y = 58 - (value / max) * 50;
    return `${x},${y}`;
  }).join(" ");
  const latest = values.at(-1) ?? 0;
  return (
    <div className="chart-card" title={`Mới nhất: ${latest} ${unit}`}>
      <div><strong>{label}</strong><span>{latest} {unit}</span></div>
      <svg viewBox="0 0 240 64" aria-label={`${label}: ${latest} ${unit}`}><polyline points={points} /></svg>
    </div>
  );
}

export default function RealtimePanel({ hosts, source, destination, onSource, onDestination, onStatus }: Props) {
  const [running, setRunning] = useState(false);
  const [interval, setIntervalValue] = useState(2);
  const [rangeMinutes, setRangeMinutes] = useState(5);
  const [history, setHistory] = useState<RealtimeMetric[]>([]);
  const [socketState, setSocketState] = useState<"idle" | "connecting" | "online" | "closed" | "error">("idle");
  const [clock, setClock] = useState(Date.now());
  const socketRef = useRef<WebSocket>();

  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    setRunning(false);
    setHistory([]);
    setSocketState("idle");
    socketRef.current?.close();
    onStatus(false);
  }, [source, destination, onStatus]);

  useEffect(() => {
    if (!running) return;
    setHistory([]);
    setSocketState("connecting");
    const socket = new WebSocket(wsUrl(source, destination, interval));
    socketRef.current = socket;
    socket.onopen = () => {
      setSocketState("online");
      onStatus(true);
    };
    socket.onclose = () => {
      setSocketState("closed");
      onStatus(false);
    };
    socket.onerror = () => {
      setSocketState("error");
      onStatus(false);
    };
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as RealtimeMetric;
        const maxPoints = Math.max(10, Math.ceil((rangeMinutes * 60) / interval));
        setHistory((current) => [...current, payload].slice(-maxPoints));
      } catch {
        setSocketState("error");
      }
    };
    return () => socket.close();
  }, [running, source, destination, interval, rangeMinutes, onStatus]);

  const latest = history.at(-1);
  const updated = useMemo(
    () => latest?.timestamp ? new Date(latest.timestamp).toLocaleTimeString("vi-VN") : "Chưa có dữ liệu",
    [latest],
  );
  const latestTime = latest?.timestamp ? new Date(latest.timestamp).getTime() : 0;
  const stale = Boolean(latestTime && clock - latestTime > interval * 3000);
  const selectableHosts = hosts.filter((host) => host.name !== (source || destination));

  return (
    <section>
      <div className="section-title">
        <div><h2>Giám sát hiệu năng theo thời gian thực</h2><span>Ping định kỳ và OpenFlow counter; không chạy iperf liên tục</span></div>
        <div className="realtime-statuses">
          <StatusBadge status={socketState === "online" ? "online" : socketState === "error" ? "offline" : socketState === "connecting" ? "degraded" : "unknown"} label={`WebSocket ${socketState}`} />
          {stale && <StatusBadge status="degraded" label="Dữ liệu stale" />}
        </div>
      </div>
      <div className="panel-body realtime-workspace">
        <div className="realtime-controls">
          <label>Nguồn
            <select value={source} disabled={running} onChange={(event) => onSource(event.target.value)}>
              {hosts.filter((host) => host.name !== destination).map((host) => <option value={host.name} key={host.name}>{host.name} · {host.group_label} · {host.ip}</option>)}
            </select>
          </label>
          <label>Đích
            <select value={destination} disabled={running} onChange={(event) => onDestination(event.target.value)}>
              {selectableHosts.filter((host) => host.name !== source).map((host) => <option value={host.name} key={host.name}>{host.name} · {host.group_label} · {host.ip}</option>)}
            </select>
          </label>
          <label>Chu kỳ
            <select value={interval} disabled={running} onChange={(event) => setIntervalValue(Number(event.target.value))}>
              <option value={2}>2 giây</option><option value={5}>5 giây</option><option value={10}>10 giây</option>
            </select>
          </label>
          <label>Khoảng thời gian
            <select value={rangeMinutes} disabled={running} onChange={(event) => setRangeMinutes(Number(event.target.value))}>
              <option value={1}>1 phút</option><option value={5}>5 phút</option><option value={15}>15 phút</option>
            </select>
          </label>
        </div>
        <div className="run-bar">
          <button className="primary" onClick={() => setRunning(true)} disabled={running || source === destination}><Play size={16} />Bắt đầu</button>
          <button onClick={() => setRunning(false)} disabled={!running}><Pause size={16} />Dừng</button>
          <span className="realtime-updated">Cập nhật cuối: {updated} · {history.length} điểm</span>
        </div>
        {!history.length && <div className="metrics-empty">Chọn cặp endpoint và bấm Bắt đầu để nhận số liệu thật từ WebSocket.</div>}
        {history.length > 0 && <div className="chart-grid">{chartFields.map((item) => <Sparkline data={history} key={item.field} {...item} />)}</div>}
        {latest && (
          <p className="realtime-note">
            Flow bytes {latest.flow_bytes.toLocaleString("vi-VN")} · trạng thái {latest.status} · {latest.message || "Đã nhận dữ liệu"}
          </p>
        )}
      </div>
    </section>
  );
}
