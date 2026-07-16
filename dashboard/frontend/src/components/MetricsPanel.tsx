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
      <div className="section-title">
        <h2>Kết quả lần đo gần nhất</h2>
        <span>MOS/R-factor là ước lượng từ RTT, loss và jitter; không phải cuộc gọi SIP/RTP hoàn chỉnh</span>
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
