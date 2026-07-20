import { ShieldAlert } from "lucide-react";
import type { Firewall, PhaseRuntimeStatus } from "../api/client";
import StatusBadge from "./ui/StatusBadge";

function counterText(value: { packets: number; bytes: number } | null | undefined) {
  return value ? `${value.packets.toLocaleString("vi-VN")} packets · ${value.bytes.toLocaleString("vi-VN")} bytes` : "Chưa có counter runtime";
}

export default function FirewallPanel({ firewalls, phase44Runtime }: { firewalls: Firewall[]; phase44Runtime?: PhaseRuntimeStatus }) {
  return (
    <section className="firewall-panel">
      <div className="section-title">
        <div><h2>Firewall Internet hai site</h2><span>nftables chỉ thực thi tại fw_hq và fw_telesale</span></div>
        <StatusBadge status={phase44Runtime?.status === "verified" ? "online" : phase44Runtime?.status === "failed" ? "offline" : "degraded"} label={`Phase 44: ${phase44Runtime?.status || "pending"}`} />
      </div>
      <div className="firewall-grid">
        {firewalls.map((firewall) => (
          <article className="firewall-card" key={firewall.name}>
            <div className="firewall-card-heading"><ShieldAlert size={18} /><strong>{firewall.name}</strong><StatusBadge status={firewall.runtime_status === "verified" ? "online" : firewall.runtime_status === "failed" ? "offline" : firewall.runtime_status === "unavailable" ? "unknown" : "degraded"} label={firewall.runtime_status || "pending"} /></div>
            <dl>
              <dt>Site</dt><dd>{firewall.site}</dd>
              <dt>Inside / Outside</dt><dd><code>{firewall.inside_interface || "--"}</code> / <code>{firewall.outside_interface || "--"}</code></dd>
              <dt>Forwarding IPv4</dt><dd>{firewall.ipv4_forwarding == null ? "Chưa có dữ liệu" : firewall.ipv4_forwarding ? "Bật" : "Tắt"}</dd>
              <dt>Table / Chain</dt><dd>{firewall.nftables_table || "inet cch_filter"} / {firewall.chain || "forward"}</dd>
              <dt>Rule count</dt><dd>{firewall.rule_count ?? "Chưa đọc runtime"}</dd>
              <dt>NAT</dt><dd>{firewall.nat?.conclusion || "NAT REQUIREMENT NOT YET CONCLUDED"}</dd>
            </dl>
            <div className="firewall-counters">
              <span>Social DENY: {counterText(firewall.counters?.social_deny)}</span>
              <span>Call ALLOW: {counterText(firewall.counters?.call_allow)}</span>
              <span>Zalo ALLOW: {counterText(firewall.counters?.zalo_allow)}</span>
              <span>Inbound DENY: {counterText(firewall.counters?.inbound_deny)}</span>
            </div>
            {firewall.error_code && <code>{firewall.error_code}</code>}
          </article>
        ))}
        {!firewalls.length && <p className="empty-inline">Chưa có inventory firewall runtime.</p>}
      </div>
      <p className="firewall-note">Trạng thái pending/unavailable là trung thực khi chưa chạy Combined Acceptance trên Ubuntu; không dùng counter 0 để giả lập runtime.</p>
    </section>
  );
}
