import { Activity, Ban, Gauge, Network, PhoneCall, Play, RotateCcw, ShieldCheck, Square } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Host, TestResult, Topology } from "../api/client";
import ConfirmDialog from "./ui/ConfirmDialog";
import StatusBadge from "./ui/StatusBadge";
import TaskProgress from "./ui/TaskProgress";
import { realtimeStatusLabel, realtimeStatusTone, type RealtimeConnectionState } from "./RealtimePanel";
import { errorGuidance, testLabels, type NetworkTestType } from "./testWorkflow";

type Action = NetworkTestType | "simulate" | "block" | "unblock";

type Props = {
  hosts: Host[];
  policyMap?: Topology["policy_map"];
  source: string;
  destination: string;
  seconds: number;
  testType: NetworkTestType;
  resultType: NetworkTestType;
  busy: boolean;
  elapsedSeconds: number;
  websocketState: RealtimeConnectionState;
  result?: TestResult;
  onSource: (value: string) => void;
  onDestination: (value: string) => void;
  onSeconds: (value: number) => void;
  onTestType: (value: NetworkTestType) => void;
  onRun: (action: Action) => void;
  onCancel: () => void;
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
  if (host.kind === "service") return host.group === "h90" ? "HQ · Voice" : "Internet / Services";
  return `${host.site} · ${host.group_label} · VLAN ${host.vlan}`;
}

function EndpointCombobox({
  label,
  value,
  hosts,
  exclude,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  hosts: Host[];
  exclude?: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const selected = hosts.find((host) => host.name === value);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return hosts
      .filter((host) => host.name !== exclude)
      .filter((host) => !needle || hostText(host).includes(needle))
      .slice(0, 60);
  }, [hosts, query, exclude]);
  useEffect(() => setActive(0), [query]);
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
          placeholder="Tìm hostname, IP, VLAN, site hoặc group..."
          value={query}
          disabled={disabled}
          onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") { event.preventDefault(); setOpen(true); setActive((index) => Math.min(index + 1, filtered.length - 1)); }
            if (event.key === "ArrowUp") { event.preventDefault(); setActive((index) => Math.max(index - 1, 0)); }
            if (event.key === "Enter" && filtered[active]) { event.preventDefault(); choose(filtered[active]); }
            if (event.key === "Escape") setOpen(false);
          }}
        />
        <button type="button" disabled={disabled} onClick={() => setOpen((current) => !current)}>{selected ? endpointLabel(selected) : "Chọn endpoint"}</button>
        {open && (
          <div className="combo-list" role="listbox">
            {groups.map(([group, items]) => (
              <div className="combo-group" key={group}>
                <strong>{group}</strong>
                {items.map((host) => {
                  const flatIndex = filtered.findIndex((item) => item.name === host.name);
                  return (
                    <button type="button" disabled={disabled} role="option" aria-selected={host.name === value} className={flatIndex === active ? "active" : ""} key={host.name}
                      onMouseDown={(event) => event.preventDefault()} onClick={() => choose(host)}>
                      <span>{endpointLabel(host)}</span>
                      <small>{host.site} · VLAN {host.vlan ?? "service"} · {host.group_label}</small>
                    </button>
                  );
                })}
              </div>
            ))}
            {!filtered.length && <p>Không tìm thấy endpoint phù hợp.</p>}
          </div>
        )}
      </div>
    </label>
  );
}

function Metric({ label, value, unit }: { label: string; value: unknown; unit?: string }) {
  return <div className="result-metric"><span>{label}</span><strong>{value == null ? "--" : String(value)}{value == null || !unit ? "" : ` ${unit}`}</strong></div>;
}

export default function TestPanel(props: Props) {
  const [confirmAction, setConfirmAction] = useState<"block" | "unblock" | null>(null);
  const sourceHost = props.hosts.find((host) => host.name === props.source);
  const destinationHost = props.hosts.find((host) => host.name === props.destination);
  const sourcePolicyId = sourceHost?.kind === "user" ? sourceHost.group : sourceHost?.name;
  const destinationPolicyId = destinationHost?.kind === "user" ? destinationHost.group : destinationHost?.name;
  const policyEntry = sourcePolicyId ? props.policyMap?.[sourcePolicyId] : undefined;
  const policyAllowed = destinationPolicyId ? policyEntry?.allow.includes(destinationPolicyId) : undefined;
  const policyNote = destinationPolicyId ? policyEntry?.notes[destinationPolicyId] : undefined;
  const metrics = props.result?.result || {};
  const decision = props.result?.decision;
  const sameEndpoint = props.source === props.destination;
  const canRun = !props.busy && !sameEndpoint && Boolean(props.source && props.destination);
  const websocketWarning = props.websocketState === "reconnecting" || props.websocketState === "error";
  const testIcons = { ping: Activity, tcp: Gauge, udp: Gauge, quality: PhoneCall };
  const ActiveIcon = testIcons[props.resultType];

  const retry = () => {
    if (!props.busy) props.onRun(props.resultType);
  };

  return (
    <section className="network-test-workspace">
      <div className="section-title">
        <div><h2>Kiểm tra kết nối</h2><span>Kết quả thật từ Mininet, OVS và iperf3</span></div>
        <StatusBadge status={realtimeStatusTone(props.websocketState)} label={realtimeStatusLabel(props.websocketState)} />
      </div>
      <div className="panel-body">
        {websocketWarning && (
          <div className="realtime-warning" role="status">
            <strong>WebSocket mất kết nối</strong>
            <p>{errorGuidance("WEBSOCKET_OFFLINE")}</p>
          </div>
        )}
        <div className="endpoint-pair-grid">
          <EndpointCombobox label="Nguồn" value={props.source} hosts={props.hosts} exclude={props.destination} disabled={props.busy} onChange={props.onSource} />
          <EndpointCombobox label="Đích" value={props.destination} hosts={props.hosts} exclude={props.source} disabled={props.busy} onChange={props.onDestination} />
        </div>
        {sameEndpoint && <p className="field-error">Nguồn và đích phải khác nhau.</p>}

        <div className="policy-preview">
          <div><strong>Policy preview</strong><StatusBadge status={policyAllowed === true ? "online" : policyAllowed === false ? "offline" : "unknown"} label={policyAllowed === true ? "ALLOW dự kiến" : policyAllowed === false ? "DENY dự kiến" : "Chưa xác định"} /></div>
          <p>{policyNote || "Chọn endpoint để xem policy preview từ backend topology payload."}</p>
        </div>

        <div className="test-config-grid">
          <div>
            <span className="field-label">Loại kiểm tra</span>
            <div className="test-type-selector">
              {(Object.keys(testLabels) as NetworkTestType[]).map((type) => {
                const Icon = testIcons[type];
                return <button className={props.testType === type ? "active" : ""} disabled={props.busy} key={type} onClick={() => props.onTestType(type)}><Icon size={16} />{testLabels[type]}</button>;
              })}
            </div>
          </div>
          <label>Thời gian đo
            <input type="number" min={1} max={30} disabled={props.busy || props.testType === "ping"} value={props.seconds}
              onChange={(event) => props.onSeconds(Math.max(1, Math.min(Number(event.target.value) || 5, 30)))} />
          </label>
        </div>

        <div className="run-bar">
          <button className="primary run-button" disabled={!canRun} onClick={() => props.onRun(props.testType)}>
            <Play size={17} /><span>Chạy {testLabels[props.testType]}</span>
          </button>
          {props.busy && <button className="danger" onClick={props.onCancel}><Square size={15} />Hủy chờ</button>}
          {!props.busy && props.result && <button onClick={retry}><RotateCcw size={15} />Chạy lại</button>}
        </div>
        {props.busy && <TaskProgress label={`Đang chạy ${testLabels[props.testType]}`} elapsedSeconds={props.elapsedSeconds} />}

        {props.result && (
          <div aria-live="polite" className={`test-result ${props.result.ok ? "success" : props.result.error_code === "POLICY_DENIED" ? "deny" : "error"}`}>
            <div className="result-heading">
              <div><ActiveIcon size={20} /><strong>{props.result.message}</strong></div>
              <StatusBadge status={props.result.ok ? "online" : "offline"} label={props.result.ok ? "Thành công" : props.result.error_code === "POLICY_DENIED" ? "Policy DENY" : "Thất bại"} />
            </div>
            {props.result.error_code && (
              <div className="error-guidance" role="alert">
                <code>{props.result.error_code}</code>
                <p>{errorGuidance(props.result.error_code)}</p>
              </div>
            )}
            {props.resultType === "ping" && (
              <div className="result-metrics-grid">
                <Metric label="Kết quả" value={decision?.action?.toUpperCase() || (props.result.ok ? "ALLOW" : "DENY")} />
                <Metric label="Packet loss" value={metrics.packet_loss_percent} unit="%" />
                <Metric label="RTT trung bình" value={metrics.rtt_avg_ms} unit="ms" />
                <Metric label="Enforcement" value={decision?.enforcement_switch || decision?.blocked_at} />
              </div>
            )}
            {props.resultType === "udp" && (
              <div className="result-metrics-grid">
                <Metric label="Throughput" value={metrics.throughput_mbps} unit="Mbps" />
                <Metric label="Jitter" value={metrics.jitter_ms} unit="ms" />
                <Metric label="Packet loss" value={metrics.packet_loss_percent} unit="%" />
                <Metric label="Datagram mất/tổng" value={`${metrics.lost_packets ?? "--"}/${metrics.total_datagrams ?? "--"}`} />
                <Metric label="Duration" value={props.result.duration || props.seconds} unit="s" />
                <Metric label="Session ID" value={props.result.session_id} />
              </div>
            )}
            {props.resultType === "tcp" && (
              <div className="result-metrics-grid">
                <Metric label="Throughput" value={metrics.throughput_mbps} unit="Mbps" />
                <Metric label="Transferred" value={metrics.transferred_bytes} unit="bytes" />
                <Metric label="Duration" value={props.result.duration || props.seconds} unit="s" />
                <Metric label="Session ID" value={props.result.session_id} />
              </div>
            )}
            {props.resultType === "quality" && (
              <>
                <div className="result-metrics-grid">
                  <Metric label="RTT" value={metrics.rtt_avg_ms} unit="ms" />
                  <Metric label="Jitter" value={metrics.jitter_ms} unit="ms" />
                  <Metric label="Packet loss" value={metrics.packet_loss_percent} unit="%" />
                  <Metric label="MOS" value={metrics.mos} />
                  <Metric label="R-factor" value={metrics.r_factor} />
                  <Metric label="Rating" value={metrics.rating} />
                </div>
                <p className="estimation-note">MOS/R-factor chỉ là ước tính từ RTT, jitter và packet loss; không phải cuộc gọi SIP/RTP thật.</p>
              </>
            )}
            {decision && (
              <div className="decision-summary">
                <strong>Reason</strong><p>{decision.reason}</p>
                <strong>Path backend</strong><p>{decision.path.join(" → ") || "Không có path"}</p>
                {decision.blocked_at && <p><strong>Chặn tại:</strong> {decision.blocked_at}</p>}
                {decision.failed_link && <p><strong>Liên kết lỗi:</strong> {decision.failed_link}</p>}
                <span>Policy {decision.policy || "n/a"} · Cookie {decision.cookie || "n/a"} · Priority {decision.priority ?? "n/a"}</span>
              </div>
            )}
            <details className="technical-output">
              <summary>Chi tiết kỹ thuật</summary>
              <pre>{props.result.raw || "Backend không trả raw output."}</pre>
            </details>
          </div>
        )}

        <details className="advanced-actions">
          <summary>Thao tác SDN nâng cao</summary>
          <div className="action-grid">
            <button onClick={() => props.onRun("simulate")} disabled={props.busy}><Network size={16} />Xem path policy</button>
            <button className="danger" onClick={() => setConfirmAction("block")} disabled={props.busy}><Ban size={16} />Chặn luồng</button>
            <button onClick={() => setConfirmAction("unblock")} disabled={props.busy}><ShieldCheck size={16} />Gỡ chặn</button>
          </div>
        </details>
      </div>
      <ConfirmDialog
        open={Boolean(confirmAction)}
        title={confirmAction === "block" ? "Chặn luồng tạm thời?" : "Gỡ chặn luồng?"}
        message={`Tác động: ${confirmAction === "block" ? "cài flow DROP" : "xóa flow DROP tạm thời"} cho ${props.source} → ${props.destination} trên OVS enforcement. Ping và packet animation tiếp theo sẽ phản ánh flow runtime mới.`}
        danger={confirmAction === "block"}
        confirmLabel={confirmAction === "block" ? "Chặn luồng" : "Gỡ chặn"}
        onClose={() => setConfirmAction(null)}
        onConfirm={() => {
          if (confirmAction) props.onRun(confirmAction);
          setConfirmAction(null);
        }}
      />
    </section>
  );
}
