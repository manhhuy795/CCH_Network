type Props = {
  metrics: Record<string, number | string | boolean | object | null>;
};

const items = [
  ["rtt_avg_ms", "RTT trung binh", "ms"],
  ["jitter_ms", "Jitter", "ms"],
  ["packet_loss_percent", "Mat goi", "%"],
  ["throughput_mbps", "Thong luong", "Mbps"],
  ["mos", "MOS uoc luong", "/ 4.5"],
  ["r_factor", "R-factor", "/ 100"],
];

export default function MetricsPanel({ metrics }: Props) {
  return (
    <section>
      <div className="section-title">
        <h2>Ket qua lan do gan nhat</h2>
        <span>MOS/R-factor la uoc luong tu RTT, loss va jitter; khong phai cuoc goi SIP/RTP hoan chinh</span>
      </div>
      <div className="metric-grid">
        {items.map(([key, label, unit]) => (
          <div className="metric" key={key}>
            <strong>{["string", "number"].includes(typeof metrics[key]) ? String(metrics[key]) : "--"} <small>{metrics[key] == null ? "" : unit}</small></strong>
            <span>{label}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
