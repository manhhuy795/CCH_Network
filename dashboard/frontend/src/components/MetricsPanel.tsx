type Props = {
  metrics: Record<string, number | string | boolean | object | null>;
};

const items = [
  ["rtt_avg_ms", "RTT trung bình", "ms"],
  ["jitter_ms", "Jitter", "ms"],
  ["packet_loss_percent", "Mất gói", "%"],
  ["throughput_mbps", "Thông lượng", "Mbps"],
  ["mos", "MOS ước lượng", "/ 4.5"],
  ["r_factor", "R-factor", "/ 100"],
];

export default function MetricsPanel({ metrics }: Props) {
  return (
    <section>
      <div className="section-title"><h2>Chỉ số đo kiểm</h2><span>Real-time theo cặp đang chọn</span></div>
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
