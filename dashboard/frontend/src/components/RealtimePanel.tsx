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
    <div className="chart-card" title={`Mới nhất: ${latest} ${unit}`}>
      <div><strong>{String(field).replaceAll("_", " ")}</strong><span>{latest} {unit}</span></div>
      <svg viewBox="0 0 240 64"><polyline points={points} /></svg>
    </div>
  );
}

export default function RealtimePanel({ source, destination, onStatus }: Props) {
  const [running, setRunning] = useState(false);
  const [interval, setIntervalValue] = useState(2);
  const [history, setHistory] = useState<RealtimeMetric[]>([]);
  const socketRef = useRef<WebSocket>();

  useEffect(() => {
    setRunning(false);
    setHistory([]);
    socketRef.current?.close();
    onStatus(false);
  }, [source, destination, onStatus]);

  useEffect(() => {
    if (!running) return;
    const socket = new WebSocket(wsUrl(source, destination, interval));
    socketRef.current = socket;
    socket.onopen = () => onStatus(true);
    socket.onclose = () => onStatus(false);
    socket.onerror = () => onStatus(false);
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as RealtimeMetric;
      setHistory((current) => [...current, payload].slice(-60));
    };
    return () => socket.close();
  }, [running, source, destination, interval, onStatus]);

  const latest = history.at(-1);
  const updated = useMemo(() => latest?.timestamp ? new Date(latest.timestamp).toLocaleTimeString("vi-VN") : "Chưa có", [latest]);

  return (
    <section>
      <div className="section-title"><h2>Giám sát real-time</h2><span>{running ? "Đang giám sát" : "Đã dừng"} · Cập nhật cuối: {updated}</span></div>
      <div className="panel-body">
        <div className="form-grid">
          <label>Chu kỳ
            <select value={interval} onChange={(event) => setIntervalValue(Number(event.target.value))}>
              <option value={2}>2 giây</option>
              <option value={5}>5 giây</option>
              <option value={10}>10 giây</option>
            </select>
          </label>
          <label>Trạng thái
            <input readOnly value={running ? `Đang giám sát ${source} → ${destination}` : "Chưa giám sát"} />
          </label>
        </div>
        <div className="action-grid">
          <button className="primary" onClick={() => setRunning(true)} disabled={running}><Play size={16} />Bắt đầu giám sát</button>
          <button onClick={() => setRunning(false)} disabled={!running}><Pause size={16} />Dừng giám sát</button>
        </div>
        <div className="chart-grid">
          <Sparkline data={history} field="throughput_mbps" unit="Mbps" />
          <Sparkline data={history} field="delay_ms" unit="ms" />
          <Sparkline data={history} field="packet_loss_percent" unit="%" />
          <Sparkline data={history} field="jitter_ms" unit="ms" />
        </div>
      </div>
    </section>
  );
}
