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
      const key = `${host.site} - ${host.group_label}`;
      data.set(key, [...(data.get(key) || []), host]);
    });
    return [...data.entries()];
  }, [filtered]);
  return (
    <label>{label}
      <input placeholder="Tim hostname, IP, project, VLAN..." value={query} onChange={(event) => setQuery(event.target.value)} />
      <select value={filtered.some((host) => host.name === value) ? value : filtered[0]?.name ?? ""} onChange={(event) => onChange(event.target.value)}>
        {groups.map(([group, items]) => (
          <optgroup label={group} key={group}>
            {items.map((host) => <option value={host.name} key={host.name}>{host.label} - {host.name} - {host.ip}</option>)}
          </optgroup>
        ))}
      </select>
    </label>
  );
}

export default function TestPanel(props: Props) {
  const decision = props.result?.decision;
  const confirmControl = (action: "block" | "unblock") => {
    const verb = action === "block" ? "cai flow DROP" : "go flow DROP";
    if (window.confirm(`Ban co chac muon ${verb} cho ${props.source} -> ${props.destination} khong?`)) {
      props.onRun(action);
    }
  };
  return (
    <section>
      <div className="section-title"><h2>Do kiem mang</h2><span>Ket qua that tu Mininet/OVS</span></div>
      <div className="panel-body">
        <div className="form-grid">
          <HostSelect label="Nguon" value={props.source} hosts={props.hosts} onChange={props.onSource} />
          <HostSelect label="Dich" value={props.destination} hosts={props.hosts} onChange={props.onDestination} />
          <label className="full">Thoi gian do chu dong (giay)<input type="number" min={1} max={60} value={props.seconds} onChange={(event) => props.onSeconds(Number(event.target.value))} /></label>
        </div>
        <h3 className="button-group-title">Do kiem mang</h3>
        <div className="action-grid">
          <button className="primary" disabled={props.busy} onClick={() => props.onRun("ping")}><Activity size={16} />Kiem tra Ping</button>
          <button disabled={props.busy} onClick={() => props.onRun("tcp")}><Gauge size={16} />Throughput TCP</button>
          <button disabled={props.busy} onClick={() => props.onRun("udp")}><Gauge size={16} />Jitter UDP</button>
          <button disabled={props.busy} onClick={() => props.onRun("quality")}><PhoneCall size={16} />Uoc luong chat luong thoai</button>
          <button disabled={props.busy} onClick={() => props.onRun("simulate")}><Network size={16} />Mo phong path</button>
        </div>
        <h3 className="button-group-title">Dieu khien SDN</h3>
        <div className="action-grid">
          <button className="danger" disabled={props.busy} onClick={() => confirmControl("block")}><Ban size={16} />Chan luong</button>
          <button disabled={props.busy} onClick={() => confirmControl("unblock")}><ShieldCheck size={16} />Go chan</button>
        </div>
        <div className={`result-box ${props.result?.ok ? "ok" : props.result ? "bad" : ""}`}>
          <strong>{props.busy ? "Dang thuc hien..." : props.result?.message || "San sang do kiem"}</strong>
          <p>{decision?.reason || "Chon tung user cu the roi chay phep do."}</p>
          {decision && (
            <div className="decision-meta">
              <span>Enforce: {decision.enforcement_switch || "n/a"}</span>
              <span>Policy: {decision.policy || "n/a"}</span>
              <span>Cookie: {decision.cookie || "n/a"}</span>
              <span>Priority: {decision.priority ?? "n/a"}</span>
              {decision.failed_link && <span>Failed link: {decision.failed_link}</span>}
            </div>
          )}
        </div>
        <pre>{props.result?.raw || "Output ping/iperf3/OVS se hien thi tai day."}</pre>
      </div>
    </section>
  );
}
