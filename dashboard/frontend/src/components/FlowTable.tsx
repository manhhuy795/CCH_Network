import { ArrowUpDown, Eye } from "lucide-react";
import { useMemo, useState } from "react";
import Drawer from "./ui/Drawer";

type Flow = Record<string, unknown>;
type SortKey = "switch" | "cookie" | "priority" | "packets" | "bytes";

function flowText(flow: Flow, key: string, fallback = "*") {
  return String(flow[key] ?? fallback);
}

function actionLabel(action: unknown) {
  if (action === "ALLOW") return "ALLOW · chuyển tiếp";
  if (action === "DROP") return "DROP · chặn";
  if (action === "PACKET_IN") return "PACKET_IN · hỏi controller";
  return String(action ?? "UNKNOWN");
}

function compareFlows(left: Flow, right: Flow, key: SortKey) {
  if (key === "priority" || key === "packets" || key === "bytes") {
    return Number(left[key] || 0) - Number(right[key] || 0);
  }
  return flowText(left, key, "").localeCompare(flowText(right, key, ""), "vi");
}

function SortButton({ field, onSort, children }: { field: SortKey; onSort: (field: SortKey) => void; children: React.ReactNode }) {
  return <button className="table-sort" onClick={() => onSort(field)}>{children}<ArrowUpDown size={12} /></button>;
}

export default function FlowTable({ flows }: { flows: Flow[] }) {
  const [actionFilter, setActionFilter] = useState("all");
  const [switchFilter, setSwitchFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("priority");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [selected, setSelected] = useState<Flow>();
  const switches = useMemo(() => [...new Set(flows.map((flow) => flowText(flow, "switch", "")).filter(Boolean))].sort(), [flows]);
  const visible = useMemo(() => flows
    .filter((flow) => {
      const text = JSON.stringify(flow).toLowerCase();
      if (query && !text.includes(query.toLowerCase())) return false;
      if (switchFilter !== "all" && flow.switch !== switchFilter) return false;
      if (actionFilter === "allow") return flow.action === "ALLOW";
      if (actionFilter === "deny") return flow.action === "DROP";
      if (actionFilter === "packet_in") return flow.action === "PACKET_IN";
      return true;
    })
    .sort((left, right) => compareFlows(left, right, sortKey) * (sortDirection === "asc" ? 1 : -1)),
  [flows, actionFilter, switchFilter, query, sortKey, sortDirection]);

  const sort = (key: SortKey) => {
    if (sortKey === key) setSortDirection((current) => current === "asc" ? "desc" : "asc");
    else {
      setSortKey(key);
      setSortDirection(key === "switch" || key === "cookie" ? "asc" : "desc");
    }
  };

  return (
    <section>
      <div className="section-title">
        <div><h2>Bảng luồng OpenFlow</h2><span>{visible.length}/{flows.length} flow đọc trực tiếp từ OVS</span></div>
      </div>
      <div className="openflow-note">
        Mỗi dòng là flow thật trên Open vSwitch. Cookie nhận diện nhóm policy; priority quyết định luật nào được xét trước; packet/byte là counter runtime.
      </div>
      <div className="flow-filters">
        <select aria-label="Lọc switch" value={switchFilter} onChange={(event) => setSwitchFilter(event.target.value)}>
          <option value="all">Tất cả switch</option>
          {switches.map((item) => <option value={item} key={item}>{item}</option>)}
        </select>
        <select aria-label="Lọc action" value={actionFilter} onChange={(event) => setActionFilter(event.target.value)}>
          <option value="all">Tất cả action</option>
          <option value="allow">ALLOW</option>
          <option value="deny">DROP</option>
          <option value="packet_in">PACKET_IN</option>
        </select>
        <input aria-label="Tìm flow" placeholder="Tìm host, IP, VLAN, match, cookie..." value={query} onChange={(event) => setQuery(event.target.value)} />
      </div>
      <div className="table-scroll">
        <table className="flow-table">
          <thead>
            <tr>
              <th><SortButton field="switch" onSort={sort}>Switch</SortButton></th>
              <th><SortButton field="cookie" onSort={sort}>Cookie</SortButton></th>
              <th><SortButton field="priority" onSort={sort}>Priority</SortButton></th>
              <th>Match</th><th>Action</th>
              <th><SortButton field="packets" onSort={sort}>Packets</SortButton></th>
              <th><SortButton field="bytes" onSort={sort}>Bytes</SortButton></th>
              <th><span className="sr-only">Chi tiết</span></th>
            </tr>
          </thead>
          <tbody>
            {visible.map((flow, index) => (
              <tr key={`${flowText(flow, "switch", "")}-${flowText(flow, "cookie")}-${index}`}>
                <td><strong>{flowText(flow, "switch", "")}</strong></td>
                <td><code>{flowText(flow, "cookie", "0x0")}</code></td>
                <td>{flowText(flow, "priority", "0")}</td>
                <td>{flowText(flow, "match", `${flowText(flow, "source")} → ${flowText(flow, "destination")}`)}</td>
                <td><span className={`pill ${flow.action === "ALLOW" ? "allow" : "deny"}`}>{actionLabel(flow.action)}</span></td>
                <td>{Number(flow.packets ?? 0).toLocaleString("vi-VN")}</td>
                <td>{Number(flow.bytes ?? 0).toLocaleString("vi-VN")}</td>
                <td><button className="icon-button" title="Xem chi tiết flow" onClick={() => setSelected(flow)}><Eye size={15} /></button></td>
              </tr>
            ))}
            {!visible.length && <tr><td colSpan={8}>Chưa đọc được flow hoặc bộ lọc không có kết quả.</td></tr>}
          </tbody>
        </table>
      </div>
      <Drawer open={Boolean(selected)} title={`Flow · ${flowText(selected || {}, "switch", "unknown")}`} onClose={() => setSelected(undefined)}>
        {selected && (
          <div className="inspector-grid">
            <dl>
              <dt>Switch</dt><dd>{flowText(selected, "switch")}</dd>
              <dt>Cookie</dt><dd>{flowText(selected, "cookie")}</dd>
              <dt>Priority</dt><dd>{flowText(selected, "priority")}</dd>
              <dt>Source</dt><dd>{flowText(selected, "source")}</dd>
              <dt>Destination</dt><dd>{flowText(selected, "destination")}</dd>
              <dt>Action</dt><dd>{actionLabel(selected.action)}</dd>
              <dt>Packets</dt><dd>{flowText(selected, "packets", "0")}</dd>
              <dt>Bytes</dt><dd>{flowText(selected, "bytes", "0")}</dd>
              <dt>Ý nghĩa</dt><dd>{flowText(selected, "reason", "Không có mô tả")}</dd>
            </dl>
            <div><h3>Match kỹ thuật</h3><pre>{flowText(selected, "raw_match", "")}</pre></div>
            <div><h3>Action kỹ thuật</h3><pre>{flowText(selected, "raw_action", "")}</pre></div>
          </div>
        )}
      </Drawer>
    </section>
  );
}
