import { Activity, Ban, Gauge, Network, PhoneCall, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Host, TestResult } from "../api/client";

type Action = "ping" | "tcp" | "udp" | "quality" | "simulate" | "block" | "unblock";

type Props = {
  hosts: Host[];
  source: string;
  destination: string;
  seconds: number;
  busy: boolean;
  result?: TestResult;
  onSource: (value: string) => void;
  onDestination: (value: string) => void;
  onSeconds: (value: number) => void;
  onRun: (action: Action) => void;
};

function hostText(host: Host) {
  return `${host.site} ${host.group_label} VLAN ${host.vlan ?? ""} ${host.label} ${host.name} ${host.ip}`.toLowerCase();
}

function HostSelect({ label, value, hosts, onChange }: { label: string; value: string; hosts: Host[]; onChange: (value: string) => void }) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? hosts.filter((host) => hostText(host).includes(needle)) : hosts;
  }, [hosts, query]);
  useEffect(() => {
    if (!filtered.length) return;
    if (!filtered.some((host) => host.name === value)) onChange(filtered[0].name);
  }, [filtered, value, onChange]);
  const groups = useMemo(() => {
    const data = new Map<string, Host[]>();
    filtered.forEach((host) => {
      const key = `${host.site} · ${host.group_label}`;
      data.set(key, [...(data.get(key) || []), host]);
    });
    return [...data.entries()];
  }, [filtered]);
  return (
    <label>{label}
      <input placeholder="Tìm hostname, IP, project, VLAN..." value={query} onChange={(event) => setQuery(event.target.value)} />
      <select value={filtered.some((host) => host.name === value) ? value : filtered[0]?.name ?? ""} onChange={(event) => onChange(event.target.value)}>
        {groups.map(([group, items]) => (
          <optgroup label={group} key={group}>
            {items.map((host) => <option value={host.name} key={host.name}>{host.label} · {host.name} · {host.ip}</option>)}
          </optgroup>
        ))}
      </select>
    </label>
  );
}

export default function TestPanel(props: Props) {
  const confirmControl = (action: "block" | "unblock") => {
    const verb = action === "block" ? "cài flow DROP" : "gỡ flow DROP";
    if (window.confirm(`Bạn có chắc muốn ${verb} cho ${props.source} → ${props.destination} không?`)) {
      props.onRun(action);
    }
  };
  return (
    <section>
      <div className="section-title"><h2>Đo kiểm mạng</h2><span>Kết quả thật từ Mininet/OVS</span></div>
      <div className="panel-body">
        <div className="form-grid">
          <HostSelect label="Nguồn" value={props.source} hosts={props.hosts} onChange={props.onSource} />
          <HostSelect label="Đích" value={props.destination} hosts={props.hosts} onChange={props.onDestination} />
          <label className="full">Thời gian đo chủ động (giây)<input type="number" min={1} max={60} value={props.seconds} onChange={(event) => props.onSeconds(Number(event.target.value))} /></label>
        </div>
        <h3 className="button-group-title">Đo kiểm mạng</h3>
        <div className="action-grid">
          <button className="primary" disabled={props.busy} onClick={() => props.onRun("ping")}><Activity size={16} />Kiểm tra Ping</button>
          <button disabled={props.busy} onClick={() => props.onRun("tcp")}><Gauge size={16} />Throughput TCP</button>
          <button disabled={props.busy} onClick={() => props.onRun("udp")}><Gauge size={16} />Jitter UDP</button>
          <button disabled={props.busy} onClick={() => props.onRun("quality")}><PhoneCall size={16} />Chất lượng thoại</button>
          <button disabled={props.busy} onClick={() => props.onRun("simulate")}><Network size={16} />Mô phỏng path</button>
        </div>
        <h3 className="button-group-title">Điều khiển SDN</h3>
        <div className="action-grid">
          <button className="danger" disabled={props.busy} onClick={() => confirmControl("block")}><Ban size={16} />Chặn luồng</button>
          <button disabled={props.busy} onClick={() => confirmControl("unblock")}><ShieldCheck size={16} />Gỡ chặn</button>
        </div>
        <div className={`result-box ${props.result?.ok ? "ok" : props.result ? "bad" : ""}`}>
          <strong>{props.busy ? "Đang thực hiện..." : props.result?.message || "Sẵn sàng đo kiểm"}</strong>
          <p>{props.result?.decision?.reason || "Chọn từng user cụ thể rồi chạy phép đo."}</p>
        </div>
        <pre>{props.result?.raw || "Output ping/iperf3/OVS sẽ hiển thị tại đây."}</pre>
      </div>
    </section>
  );
}
