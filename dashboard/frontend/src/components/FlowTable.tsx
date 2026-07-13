export default function FlowTable({ flows }: { flows: Array<Record<string, unknown>> }) {
  return (
    <section>
      <div className="section-title"><h2>Bảng flow OpenFlow</h2><span>{flows.length} flow đọc từ 8 OVS</span></div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Switch</th><th>Nguồn</th><th>Đích</th><th>Quyết định</th>
              <th>Ưu tiên</th><th>Match</th><th>Action</th><th>Packet</th><th>Byte</th><th>Lý do</th>
            </tr>
          </thead>
          <tbody>
            {flows.map((flow, index) => (
              <tr key={index}>
                <td>{String(flow.switch ?? "")}</td>
                <td>{String(flow.source ?? "*")}</td>
                <td>{String(flow.destination ?? "*")}</td>
                <td><span className={`pill ${flow.action === "ALLOW" ? "allow" : "deny"}`}>{String(flow.action)}</span></td>
                <td>{String(flow.priority ?? 0)}</td>
                <td>{String(flow.raw_match ?? "")}</td>
                <td>{String(flow.raw_action ?? "")}</td>
                <td>{String(flow.packets ?? 0)}</td>
                <td>{String(flow.bytes ?? 0)}</td>
                <td>{String(flow.reason ?? "")}</td>
              </tr>
            ))}
            {flows.length === 0 && <tr><td colSpan={10}>Chưa đọc được flow. Hãy chạy controller và topology.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
