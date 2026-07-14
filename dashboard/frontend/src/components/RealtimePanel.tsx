import { Pause, Play } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { RealtimeMetric } from "../api/client";
import { wsUrl } from "../api/client";

type Props = {
  source: string;
  destination: string;
  onStatus: (connected: boolean) => void;
};

function Sparkline({ data, field, unit }: { data: RealtimeMetric[]; field: keyof RealtimeMetric; unit: string }) {
  const values = data.map((item) => Number(item[field] ?? 0));
  const max = Math.max(1, ...values);
  const points = values.map((value, index) => {
    const x = data.length <= 1 ? 0 : (index / (data.length - 1)) * 240;
    const y = 58 - (value / max) * 50;
    return `${x},${y}`;
  }).join(" ");
  const latest = values.at(-1) ?? 0;
  return (
    <div className="chart-card" title={`Moi nhat: ${latest} ${unit}`}>
      <div><strong>{String(field).replaceAll("_", " ")}</strong><span>{latest} {unit}</span></div>
      <svg viewBox="0 0 240 64"><polyline points={points} /></svg>
    </div>
  );
}

export default function RealtimePanel({ source, destination, onStatus }: Props) {
  const [running, setRunning] = useState(false);
  const [interval, setIntervalValue] = useState(2);
  const [history, setHistory] = useState<RealtimeMetric[]>([]);
  const [socketState, setSocketState] = useState<"idle" | "connecting" | "online" | "closed" | "error">("idle");
  const socketRef = useRef<WebSocket>();

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
      const payload = JSON.parse(event.data) as RealtimeMetric;
      setHistory((current) => [...current, payload].slice(-60));
    };
    return () => socket.close();
  }, [running, source, destination, interval, onStatus]);

  const latest = history.at(-1);
  const updated = useMemo(
    () => latest?.timestamp ? new Date(latest.timestamp).toLocaleTimeString("vi-VN") : "Chua co",
    [latest],
  );

  return (
    <section>
      <div className="section-title">
        <h2>Giam sat theo thoi gian thuc</h2>
        <span>{socketState} - cap nhat cuoi: {updated} - {history.length}/60 diem</span>
      </div>
      <div className="panel-body">
        <div className="form-grid">
          <label>Chu ky
            <select value={interval} onChange={(event) => setIntervalValue(Number(event.target.value))}>
              <option value={2}>2 giay</option>
              <option value={5}>5 giay</option>
              <option value={10}>10 giay</option>
            </select>
          </label>
          <label>Trang thai
            <input readOnly value={running ? `Dang giam sat ${source} -> ${destination}` : "Da dung"} />
          </label>
        </div>
        <div className="action-grid">
          <button className="primary" onClick={() => setRunning(true)} disabled={running}><Play size={16} />Bat dau giam sat</button>
          <button onClick={() => setRunning(false)} disabled={!running}><Pause size={16} />Dung giam sat</button>
        </div>
        <div className="chart-grid">
          <Sparkline data={history} field="throughput_mbps" unit="Mbps" />
          <Sparkline data={history} field="delay_ms" unit="ms" />
          <Sparkline data={history} field="packet_loss_percent" unit="%" />
          <Sparkline data={history} field="jitter_ms" unit="ms" />
        </div>
        {latest && (
          <p className="realtime-note">
            Flow packets {latest.flow_packets} - flow bytes {latest.flow_bytes} - status {latest.status}
          </p>
        )}
      </div>
    </section>
  );
}
