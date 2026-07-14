const labels: Record<string, string> = {
  isolate_hq_projects: "Cách ly các dự án tại HQ",
  isolate_branch_vlan_50_60: "Cách ly VLAN 50 và VLAN 60",
  allow_voice: "Cho phép Voice Service",
  allow_zalo: "Cho phép Zalo",
  allow_call_app: "Cho phép Call App / CRM",
  allow_general_internet: "Cho phép General Internet",
  block_social_media: "Chặn Social Media",
  allow_it_support_controlled_access: "IT Support quản trị có kiểm soát",
  voice_flow_priority: "Voice Flow Priority",
  intersite_via_mpls_l3vpn: "Liên site qua MPLS L3VPN Logic Cloud",
};

type Props = {
  policies: Record<string, unknown>;
  onToggle?: (key: string, enabled: boolean) => void;
  busy?: boolean;
};

export default function PolicyPanel({ policies, onToggle, busy = false }: Props) {
  const policyData = (policies.policies || {}) as Record<string, unknown>;
  return (
    <section>
      <div className="section-title"><h2>Chính sách SDN Edge</h2><span>Mặc định từ chối</span></div>
      <div className="policy-list">
        {Object.entries(policyData).filter(([, value]) => typeof value === "boolean").map(([key, value]) => (
          <div key={key}>
            <span>{labels[key] || key.replaceAll("_", " ")}</span>
            <strong className={value ? "enabled" : "disabled"}>{value ? "Bật" : "Tắt"}</strong>
            {onToggle && <button disabled={busy} onClick={() => onToggle(key, !value)}>{value ? "Tắt" : "Bật"}</button>}
          </div>
        ))}
      </div>
      <div className="explanation">
        <h3>Chốt nơi thực thi policy</h3>
        <p>Project isolation drop tại HQ Core SDN/L3. VLAN 50/60 và Social Media của Branch drop tại Branch Distribution SDN/L3.</p>
        <p>Controller chỉ điều khiển OVS qua OpenFlow 1.3. CE, Firewall và MPLS L3VPN Logic Cloud không nằm trong OpenFlow control domain.</p>
        <p>Toggle policy sẽ ghi `policy.yml` atomic và chỉ báo thành công khi OS-Ken xác nhận reload.</p>
      </div>
    </section>
  );
}
