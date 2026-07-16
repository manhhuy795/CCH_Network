import { Clipboard } from "lucide-react";
import { useMemo, useState } from "react";
import type { ActivityEvent, TaskHistoryItem } from "../api/client";
import StatusBadge from "./ui/StatusBadge";

export type LogEntry = ActivityEvent;

function eventTime(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("vi-VN");
}

function eventTone(severity: ActivityEvent["severity"]) {
  if (severity === "error") return "offline";
  if (severity === "warning") return "degraded";
  return "online";
}

export default function EventLog({ entries, tasks }: { entries: ActivityEvent[]; tasks: TaskHistoryItem[] }) {
  const [filterReferenceTime] = useState(() => Date.now());
  const [timeRange, setTimeRange] = useState("all");
  const [severity, setSeverity] = useState("all");
  const [component, setComponent] = useState("all");
  const [eventType, setEventType] = useState("all");
  const [pairQuery, setPairQuery] = useState("");
  const components = [...new Set(entries.map((entry) => entry.component))].sort();
  const eventTypes = [...new Set(entries.map((entry) => entry.event_type))].sort();
  const visible = useMemo(() => {
    const rangeMs = timeRange === "15m" ? 15 * 60_000 : timeRange === "1h" ? 3_600_000 : timeRange === "24h" ? 86_400_000 : 0;
    const needle = pairQuery.trim().toLowerCase();
    return entries.filter((entry) => {
      if (rangeMs && filterReferenceTime - new Date(entry.timestamp).getTime() > rangeMs) return false;
      if (severity !== "all" && entry.severity !== severity) return false;
      if (component !== "all" && entry.component !== component) return false;
      if (eventType !== "all" && entry.event_type !== eventType) return false;
      if (needle && !`${entry.source || ""} ${entry.destination || ""}`.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [entries, timeRange, severity, component, eventType, pairQuery, filterReferenceTime]);

  const copyDetail = async (entry: ActivityEvent) => {
    await navigator.clipboard.writeText(JSON.stringify(entry.technical_detail || entry, null, 2));
  };

  return (
    <div className="events-workspace">
      <section>
        <div className="section-title"><div><h2>Sự kiện & nhật ký</h2><span>{visible.length}/{entries.length} sự kiện có cấu trúc</span></div></div>
        <div className="event-filters">
          <select aria-label="Lọc thời gian" value={timeRange} onChange={(event) => setTimeRange(event.target.value)}>
            <option value="all">Mọi thời gian</option><option value="15m">15 phút</option><option value="1h">1 giờ</option><option value="24h">24 giờ</option>
          </select>
          <select aria-label="Lọc severity" value={severity} onChange={(event) => setSeverity(event.target.value)}>
            <option value="all">Mọi severity</option><option value="info">Info</option><option value="warning">Warning</option><option value="error">Error</option>
          </select>
          <select aria-label="Lọc component" value={component} onChange={(event) => setComponent(event.target.value)}>
            <option value="all">Mọi component</option>{components.map((item) => <option key={item}>{item}</option>)}
          </select>
          <select aria-label="Lọc event type" value={eventType} onChange={(event) => setEventType(event.target.value)}>
            <option value="all">Mọi event type</option>{eventTypes.map((item) => <option key={item}>{item}</option>)}
          </select>
          <input aria-label="Lọc source destination" placeholder="Source hoặc destination..." value={pairQuery} onChange={(event) => setPairQuery(event.target.value)} />
        </div>
        <div className="structured-events">
          {!visible.length && <p className="empty-inline">Không có sự kiện phù hợp bộ lọc.</p>}
          {visible.map((entry) => (
            <article className="structured-event" key={entry.id}>
              <div>
                <StatusBadge status={eventTone(entry.severity)} label={entry.severity.toUpperCase()} />
                <strong>{entry.event_type}</strong>
                <span>{entry.component}</span>
                <time>{eventTime(entry.timestamp)}</time>
                <button className="icon-button" title="Sao chép chi tiết kỹ thuật" onClick={() => void copyDetail(entry)}><Clipboard size={14} /></button>
              </div>
              <p>{entry.message}</p>
              {(entry.source || entry.destination) && <small>{entry.source || "N/A"} → {entry.destination || "N/A"} {entry.error_code ? `· ${entry.error_code}` : ""}</small>}
            </article>
          ))}
        </div>
      </section>
      <section>
        <div className="section-title"><h2>Lịch sử tác vụ</h2><span>{tasks.length} tác vụ gần nhất</span></div>
        <div className="table-scroll">
          <table className="task-history-table">
            <thead><tr><th>Task ID</th><th>Thao tác</th><th>Trạng thái</th><th>Bắt đầu</th><th>Kết thúc</th><th>Duration</th><th>Kết quả</th><th>Error</th></tr></thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.task_id}>
                  <td><code>{task.task_id}</code></td><td>{task.user_action}</td>
                  <td><StatusBadge status={task.status === "success" ? "online" : task.status === "failed" ? "offline" : "degraded"} label={task.status} /></td>
                  <td>{eventTime(task.started_at)}</td><td>{task.ended_at ? eventTime(task.ended_at) : "--"}</td>
                  <td>{task.duration_ms == null ? "--" : `${task.duration_ms} ms`}</td>
                  <td>{task.result_summary || "--"}</td><td>{task.error_code || "--"}</td>
                </tr>
              ))}
              {!tasks.length && <tr><td colSpan={8}>Chưa có task history từ backend.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
