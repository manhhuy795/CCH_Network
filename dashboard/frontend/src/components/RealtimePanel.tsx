import { Pause, Play } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Host, RealtimeMetric } from "../api/client";
import { wsUrl } from "../api/client";
import StatusBadge from "./ui/StatusBadge";

export type RealtimeConnectionState = "idle" | "connecting" | "connected" | "monitoring" | "reconnecting" | "stopped" | "error";

const MAX_RECONNECT_ATTEMPTS = 5;

export function realtimeStatusLabel(state: RealtimeConnectionState) {
  const labels: Record<RealtimeConnectionState, string> = {
    idle: "Chưa bật giám sát",
    connecting: "Đang kết nối",
    connected: "Realtime đã kết nối",
    monitoring: "Đang giám sát",
    reconnecting: "Đang kết nối lại",
    stopped: "Đã dừng giám sát",
    error: "Lỗi kết nối",
  };
  return labels[state];
}

export function realtimeStatusTone(state: RealtimeConnectionState) {
  if (state === "connected" || state === "monitoring") return "online" as const;
  if (state === "connecting" || state === "reconnecting") return "degraded" as const;
  if (state === "error") return "offline" as const;
  return "unknown" as const;
}

type Props = {
  hosts: Host[];
  source: string;
  destination: string;
  onSource: (value: string) => void;
  onDestination: (value: string) => void;
  onStatus: (state: RealtimeConnectionState) => void;
};

const chartFields: Array<{ field: keyof RealtimeMetric; label: string; unit: string }> = [
  { field: "throughput_mbps", label: "Throughput theo flow counter", unit: "Mbps" },
  { field: "delay_ms", label: "RTT trung bình", unit: "ms" },
  { field: "jitter_ms", label: "Jitter", unit: "ms" },
  { field: "packet_loss_percent", label: "Packet loss", unit: "%" },
  { field: "flow_packets", label: "Flow packets", unit: "packets" },
];

function Sparkline({ data, field, label, unit }: { data: RealtimeMetric[]; field: keyof RealtimeMetric; label: string; unit: string }) {
  const values = data.map((item) => typeof item[field] === "number" ? item[field] as number : null);
  const observed = values.filter((value): value is number => value !== null);
  const max = Math.max(1, ...observed);
  const points = observed.map((value, index) => {
    const x = observed.length <= 1 ? 0 : (index / (observed.length - 1)) * 240;
    const y = 58 - (value / max) * 50;
    return `${x},${y}`;
  }).join(" ");
  const latest = values.at(-1);
  const latestLabel = latest === null || latest === undefined ? "Chưa có dữ liệu runtime" : `${latest} ${unit}`;
  return (
    <div className="chart-card" title={`Mới nhất: ${latestLabel}`}>
      <div><strong>{label}</strong><span>{latestLabel}</span></div>
      <svg viewBox="0 0 240 64" aria-label={`${label}: ${latestLabel}`}>{observed.length > 0 && <polyline points={points} />}</svg>
    </div>
  );
}

export default function RealtimePanel({ hosts, source, destination, onSource, onDestination, onStatus }: Props) {
  const [running, setRunning] = useState(false);
  const [interval, setIntervalValue] = useState(2);
  const [rangeMinutes, setRangeMinutes] = useState(5);
  const [history, setHistory] = useState<RealtimeMetric[]>([]);
  const [socketState, setSocketState] = useState<RealtimeConnectionState>("idle");
  const [reconnectNonce, setReconnectNonce] = useState(0);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [clock, setClock] = useState(() => Date.now());
  const socketRef = useRef<WebSocket>();
  const reconnectTimer = useRef<number>();
  const reconnectAttemptRef = useRef(0);

  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    setRunning(false);
    setHistory([]);
    setSocketState("idle");
    setReconnectAttempt(0);
    reconnectAttemptRef.current = 0;
    socketRef.current?.close();
    onStatus("idle");
  }, [source, destination, onStatus]);

  useEffect(() => {
    if (!running) return;
    let disposed = false;
    setSocketState("connecting");
    onStatus("connecting");
    const socket = new WebSocket(wsUrl(source, destination, interval));
    socketRef.current = socket;
    socket.onopen = () => {
      setSocketState("monitoring");
      setReconnectAttempt(0);
      reconnectAttemptRef.current = 0;
      onStatus("monitoring");
    };
    socket.onclose = () => {
      if (disposed) return;
      const nextAttempt = reconnectAttemptRef.current + 1;
      reconnectAttemptRef.current = nextAttempt;
      if (nextAttempt > MAX_RECONNECT_ATTEMPTS) {
        setSocketState("error");
        onStatus("error");
        return;
      }
      setSocketState("reconnecting");
      onStatus("reconnecting");
      setReconnectAttempt(nextAttempt);
      const delay = Math.min(5000, 800 * (2 ** (nextAttempt - 1)));
      reconnectTimer.current = window.setTimeout(() => setReconnectNonce((current) => current + 1), delay);
    };
    socket.onerror = () => {
      setSocketState("error");
      onStatus("error");
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
    return () => {
      disposed = true;
      window.clearTimeout(reconnectTimer.current);
      socket.close();
    };
  }, [running, source, destination, interval, rangeMinutes, reconnectNonce, onStatus]);

  const latest = history.at(-1);
  const updated = useMemo(
    () => latest?.timestamp ? new Date(latest.timestamp).toLocaleTimeString("vi-VN") : "Chưa có dữ liệu",
    [latest],
  );
  const latestTime = latest?.timestamp ? new Date(latest.timestamp).getTime() : 0;
  const stale = Boolean(latestTime && clock - latestTime > interval * 3000);
  const selectableHosts = hosts.filter((host) => host.name !== (source || destination));
  const stopMonitoring = () => {
    setRunning(false);
    setSocketState("stopped");
    setReconnectAttempt(0);
    reconnectAttemptRef.current = 0;
    onStatus("stopped");
  };

  return (
    <section>
      <div className="section-title">
        <div><h2>Giám sát hiệu năng theo thời gian thực</h2><span>Ping định kỳ và OpenFlow counter; không chạy iperf liên tục</span></div>
        <div className="realtime-statuses">
          <StatusBadge status={realtimeStatusTone(socketState)} label={reconnectAttempt ? `WebSocket reconnect lần ${reconnectAttempt}` : realtimeStatusLabel(socketState)} />
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
          <button onClick={stopMonitoring} disabled={!running}><Pause size={16} />Dừng</button>
          <span className="realtime-updated">Cập nhật cuối: {updated} · {history.length} điểm</span>
        </div>
        {!history.length && <div className="metrics-empty">Chọn cặp endpoint và bấm Bắt đầu để nhận số liệu thật từ WebSocket.</div>}
        {history.length > 0 && <div className="chart-grid">{chartFields.map((item) => <Sparkline data={history} key={item.field} {...item} />)}</div>}
        {latest && (
          <p className="realtime-note">
            {latest.metric_state === "unavailable" ? "Flow counter: chưa khả dụng" : `Flow bytes ${latest.flow_bytes.toLocaleString("vi-VN")}`} · trạng thái {latest.status} · {latest.message || "Đã nhận dữ liệu"}
          </p>
        )}
      </div>
    </section>
  );
}
