export type LogEntry = {
  time: string;
  message: string;
  kind: "info" | "allow" | "deny";
};

export default function EventLog({ entries }: { entries: LogEntry[] }) {
  return (
    <section>
      <div className="section-title"><h2>Nhật ký sự kiện</h2><span>{entries.length} sự kiện</span></div>
      <div className="event-categories">
        {["Packet-In", "FlowMod", "policy reload", "link down/up", "measurement", "warning", "error"].map((item) => (
          <span key={item}>{item}</span>
        ))}
      </div>
      <div className="event-log">
        {entries.length === 0 && <p>Chưa có thao tác đo kiểm.</p>}
        {entries.map((entry, index) => (
          <div className={`event ${entry.kind}`} key={`${entry.time}-${index}`}>
            <time>{entry.time}</time><span>{entry.message}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
