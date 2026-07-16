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

function endpointLabel(host?: Host) {
  if (!host) return "";
  const user = host.label.includes(" - ") ? host.label.split(" - ").slice(1).join(" - ") : host.label;
  return `${host.group_label} · ${user} · ${host.name} · ${host.ip}`;
}

function groupBucket(host: Host) {
  if (host.kind === "service") return host.group === "h90" ? "HQ - Voice" : "Service";
  return `${host.site} - ${host.group_label}`;
}

function EndpointCombobox({ label, value, hosts, onChange }: { label: string; value: string; hosts: Host[]; onChange: (value: string) => void }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const selected = hosts.find((host) => host.name === value);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (needle ? hosts.filter((host) => hostText(host).includes(needle)) : hosts).slice(0, 40);
  }, [hosts, query]);
  useEffect(() => {
    setActive(0);
  }, [query]);
  const groups = useMemo(() => {
    const data = new Map<string, Host[]>();
    filtered.forEach((host) => {
      const key = groupBucket(host);
      data.set(key, [...(data.get(key) || []), host]);
    });
    return [...data.entries()];
  }, [filtered]);
  const choose = (host: Host) => {
    onChange(host.name);
    setQuery("");
    setOpen(false);
  };
  return (
    <label className="combo-field">{label}
      <div className="endpoint-combobox" role="combobox" aria-expanded={open} aria-haspopup="listbox">
        <input
          aria-label={`${label} endpoint`}
          placeholder={selected ? endpointLabel(selected) : "Tim hostname, IP, VLAN, Project, site..."}
          value={query}
          onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); setActive((index) => Math.min(index + 1, filtered.length - 1)); }
            if (event.key === "ArrowUp") { event.preventDefault(); setActive((index) => Math.max(index - 1, 0)); }
            if (event.key === "Enter" && filtered[active]) { event.preventDefault(); choose(filtered[active]); }
            if (event.key === "Escape") setOpen(false);
          }}
        />
        <button type="button" onClick={() => setOpen((current) => !current)}>{selected ? endpointLabel(selected) : "Chon endpoint"}</button>
        {open && (
          <div className="combo-list" role="listbox">
            {groups.map(([group, items]) => (
              <div className="combo-group" key={group}>
                <strong>{group}</strong>
                {items.map((host) => {
                  const flatIndex = filtered.findIndex((item) => item.name === host.name);
                  return (
                    <button
                      type="button"
                      role="option"
                      aria-selected={host.name === value}
                      className={flatIndex === active ? "active" : ""}
                      value={host.name}
                      key={host.name}
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => choose(host)}
                    >
                      <span>{endpointLabel(host)}</span>
                      <small>{host.site} · VLAN {host.vlan ?? "service"} · {host.group_label}</small>
                    </button>
                  );
                })}
              </div>
            ))}
            {!filtered.length && <p>Khong tim thay endpoint phu hop.</p>}
          </div>
        )}
      </div>
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
          <EndpointCombobox label="Nguon" value={props.source} hosts={props.hosts} onChange={props.onSource} />
          <EndpointCombobox label="Dich" value={props.destination} hosts={props.hosts} onChange={props.onDestination} />
          <label className="full">Thoi gian do chu dong (giay)<input type="number" min={1} max={30} value={props.seconds} onChange={(event) => props.onSeconds(Number(event.target.value))} /></label>
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
          {(props.result?.error_code || props.result?.parse_warning || props.result?.cleanup_warning) && (
            <div className="decision-meta">
              {props.result.error_code && <span>Error: {props.result.error_code}</span>}
              {props.result.parse_warning && <span>Parse: {props.result.parse_warning}</span>}
              {props.result.cleanup_warning && <span>Cleanup: {props.result.cleanup_warning}</span>}
            </div>
          )}
        </div>
        <pre>{props.result?.raw || "Output ping/iperf3/OVS se hien thi tai day."}</pre>
      </div>
    </section>
  );
}
