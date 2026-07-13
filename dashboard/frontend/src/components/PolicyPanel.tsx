const labels: Record<string, string> = {
  isolate_hq_projects: "Cách ly các dự án tại HQ",
  isolate_branch_vlan_50_60: "Cách ly VLAN 50 và VLAN 60",
  allow_voice: "Cho phép dịch vụ thoại",
  allow_zalo: "Cho phép Zalo",
  allow_call_app: "Cho phép Call App / CRM",
  allow_general_internet: "Cho phép Internet chung",
  block_social_media: "Chặn mạng xã hội",
  allow_it_support_full_access: "Phòng IT được quyền remote/support",
  voice_priority: "Ưu tiên lưu lượng thoại",
  intersite_via_mpls_l3vpn: "Liên site qua MPLS L3VPN",
};

export default function PolicyPanel({ policies }: { policies: Record<string, unknown> }) {
  const policyData = (policies.policies || {}) as Record<string, unknown>;
  return (
    <section>
      <div className="section-title"><h2>Chính sách SDN Edge</h2><span>Mặc định từ chối</span></div>
      <div className="policy-list">
        {Object.entries(policyData).filter(([, value]) => typeof value === "boolean").map(([key, value]) => (
          <div key={key}><span>{labels[key] || key.replaceAll("_", " ")}</span><strong className={value ? "enabled" : "disabled"}>{value ? "Bật" : "Tắt"}</strong></div>
        ))}
      </div>
      <div className="explanation">
        <h3>SDN hoạt động như thế nào?</h3>
        <p>Open vSwitch gửi Packet-In khi chưa có rule. Controller kiểm tra policy và cài Flow-Mod; các gói tiếp theo được switch xử lý trực tiếp.</p>
        <p>Controller chỉ điều khiển OVS qua OpenFlow 1.3. MPLS L3VPN là WAN transport và không bị controller điều khiển.</p>
      </div>
    </section>
  );
}
