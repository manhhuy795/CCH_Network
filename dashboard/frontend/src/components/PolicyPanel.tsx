const labels: Record<string, string> = {
  isolate_hq_projects: "Cach ly cac du an tai HQ",
  isolate_branch_vlan_50_60: "Cach ly VLAN 50 va VLAN 60",
  allow_voice: "Cho phep Voice Service",
  allow_zalo: "Cho phep Zalo",
  allow_call_app: "Cho phep Call App / CRM",
  allow_general_internet: "Cho phep General Internet",
  block_social_media: "Chan Social Media",
  allow_it_support_controlled_access: "IT Support quan tri co kiem soat",
  voice_flow_priority: "Voice Flow Priority",
  intersite_via_mpls_l3vpn: "Lien site qua MPLS L3VPN Logic Cloud",
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
      <div className="section-title"><h2>Chinh sach SDN Edge</h2><span>Mac dinh tu choi</span></div>
      <div className="policy-list">
        {Object.entries(policyData).filter(([, value]) => typeof value === "boolean").map(([key, value]) => (
          <div key={key}>
            <span>{labels[key] || key.replaceAll("_", " ")}</span>
            <strong className={value ? "enabled" : "disabled"}>{value ? "Bat" : "Tat"}</strong>
            {onToggle && <button disabled={busy} onClick={() => onToggle(key, !value)}>{value ? "Tat" : "Bat"}</button>}
          </div>
        ))}
      </div>
      <div className="explanation">
        <h3>Chot noi thuc thi policy</h3>
        <p>Project isolation drop tai HQ Core SDN/L3. VLAN 50/60 va Social Media cua Branch drop tai Branch Distribution SDN/L3.</p>
        <p>Controller chi dieu khien OVS qua OpenFlow 1.3. CE, Internet Edge Boundary va MPLS L3VPN Logic Cloud khong nam trong OpenFlow control domain.</p>
        <p>Toggle policy ghi policy.yml atomic va chi bao thanh cong khi OS-Ken xac nhan reload.</p>
      </div>
    </section>
  );
}
