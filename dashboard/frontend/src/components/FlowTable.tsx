import { useMemo, useState } from "react";

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
        <div><h2>Bảng luồng OpenFlow dễ đọc</h2><span>{visible.length}/{flows.length} flow đọc từ OVS</span></div>
        <button onClick={() => setDetails((value) => !value)}>{details ? "Ẩn chi tiết OpenFlow" : "Xem chi tiết OpenFlow"}</button>
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
              <th>Switch</th><th>Luồng</th><th>Quyết định</th><th>Số gói</th><th>Số byte</th><th>Lý do</th>
              {details && <><th>Priority</th><th>Match</th><th>Actions</th></>}
            </tr>
          </thead>
          <tbody>
            {visible.map((flow, index) => (
              <tr key={index}>
                <td>{String(flow.switch ?? "")}</td>
                <td>{String(flow.match ?? `${flow.source ?? "*"} → ${flow.destination ?? "*"}`)}</td>
                <td><span className={`pill ${flow.action === "ALLOW" ? "allow" : "deny"}`}>{String(flow.action)}</span></td>
                <td>{String(flow.packets ?? 0)}</td>
                <td>{String(flow.bytes ?? 0)}</td>
                <td>{String(flow.reason ?? "")}</td>
                {details && <><td>{String(flow.priority ?? 0)}</td><td>{String(flow.raw_match ?? "")}</td><td>{String(flow.raw_action ?? "")}</td></>}
              </tr>
            ))}
            {visible.length === 0 && <tr><td colSpan={details ? 9 : 6}>Chưa đọc được flow hoặc bộ lọc không có kết quả.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
