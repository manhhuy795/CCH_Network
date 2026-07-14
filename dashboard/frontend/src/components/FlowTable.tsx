import { useMemo, useState } from "react";

function flowText(flow: Record<string, unknown>, key: string, fallback = "*") {
  return String(flow[key] ?? fallback);
}

function actionLabel(action: unknown) {
  if (action === "ALLOW") return "ALLOW - cho đi";
  if (action === "DROP") return "DROP - chặn";
  if (action === "PACKET_IN") return "PACKET_IN - hỏi controller";
  return String(action ?? "");
}

export default function FlowTable({ flows }: { flows: Array<Record<string, unknown>> }) {
  const [details, setDetails] = useState(false);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const visible = useMemo(() => flows.filter((flow) => {
    const text = JSON.stringify(flow).toLowerCase();
    if (query && !text.includes(query.toLowerCase())) return false;
    if (filter === "allow") return flow.action === "ALLOW";
    if (filter === "deny") return flow.action === "DROP";
    if (filter === "voice") return text.includes("voice") || text.includes("h90");
    if (filter === "it") return text.includes("it_support") || text.includes("h70");
    if (filter === "social") return text.includes("social") || text.includes("hsocial");
    if (filter === "intersite") return text.includes("mpls") || text.includes("branch") || text.includes("hq");
    return true;
  }), [flows, filter, query]);
  return (
    <section>
      <div className="section-title">
        <div><h2>Bảng luồng OpenFlow</h2><span>{visible.length}/{flows.length} flow đang đọc trực tiếp từ OVS</span></div>
        <button onClick={() => setDetails((value) => !value)}>{details ? "Ẩn match/action thô" : "Xem match/action thô"}</button>
      </div>
      <div className="openflow-note">
        OpenFlow là luật controller ghi xuống Open vSwitch: gói nào được chuyển tiếp, gói nào bị chặn, và mỗi flow đã đi bao nhiêu packet/byte.
      </div>
      <div className="flow-filters">
        <select value={filter} onChange={(event) => setFilter(event.target.value)}>
          <option value="all">Tất cả</option>
          <option value="allow">Cho phép</option>
          <option value="deny">Chặn</option>
          <option value="voice">Voice</option>
          <option value="it">IT Support</option>
          <option value="intersite">Liên site</option>
          <option value="social">Social Media</option>
        </select>
        <input placeholder="Tìm hostname, IP, switch, VLAN..." value={query} onChange={(event) => setQuery(event.target.value)} />
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>OVS</th><th>Nguồn</th><th>Đích</th><th>Hành động</th><th>Packet</th><th>Byte</th><th>Ý nghĩa</th>
              {details && <><th>Priority</th><th>Match</th><th>Actions</th></>}
            </tr>
          </thead>
          <tbody>
            {visible.map((flow, index) => (
              <tr key={index}>
                <td><strong>{flowText(flow, "switch", "")}</strong></td>
                <td>{flowText(flow, "source")}</td>
                <td>{flowText(flow, "destination")}</td>
                <td><span className={`pill ${flow.action === "ALLOW" ? "allow" : "deny"}`}>{actionLabel(flow.action)}</span></td>
                <td>{Number(flow.packets ?? 0).toLocaleString("vi-VN")}</td>
                <td>{Number(flow.bytes ?? 0).toLocaleString("vi-VN")}</td>
                <td>{String(flow.reason ?? "")}</td>
                {details && <><td>{String(flow.priority ?? 0)}</td><td>{String(flow.raw_match ?? "")}</td><td>{String(flow.raw_action ?? "")}</td></>}
              </tr>
            ))}
            {visible.length === 0 && <tr><td colSpan={details ? 10 : 7}>Chưa đọc được flow hoặc bộ lọc không có kết quả.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
