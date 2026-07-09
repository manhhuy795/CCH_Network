import { Activity, Ban, Gauge, Network, PhoneCall, ShieldCheck } from "lucide-react";
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

export default function TestPanel(props: Props) {
  const options = props.hosts.map((host) => (
    <option value={host.name} key={host.name}>{host.label} ({host.name} - {host.ip})</option>
  ));
  return (
    <section>
      <div className="section-title"><h2>Đo kiểm và điều khiển</h2><span>Kết quả thật từ Mininet</span></div>
      <div className="panel-body">
        <div className="form-grid">
          <label>Nguồn<select value={props.source} onChange={(event) => props.onSource(event.target.value)}>{options}</select></label>
          <label>Đích<select value={props.destination} onChange={(event) => props.onDestination(event.target.value)}>{options}</select></label>
          <label className="full">Thời gian đo (giây)<input type="number" min={1} max={60} value={props.seconds} onChange={(event) => props.onSeconds(Number(event.target.value))} /></label>
        </div>
        <div className="action-grid">
          <button className="primary" disabled={props.busy} onClick={() => props.onRun("ping")}><Activity size={16} />Ping thực tế</button>
          <button className="primary" disabled={props.busy} onClick={() => props.onRun("quality")}><PhoneCall size={16} />Chất lượng thoại</button>
          <button disabled={props.busy} onClick={() => props.onRun("tcp")}><Gauge size={16} />Thông lượng TCP</button>
          <button disabled={props.busy} onClick={() => props.onRun("udp")}><Gauge size={16} />Jitter UDP</button>
          <button disabled={props.busy} onClick={() => props.onRun("simulate")}><Network size={16} />Mô phỏng path</button>
          <button className="danger" disabled={props.busy} onClick={() => props.onRun("block")}><Ban size={16} />Chặn OpenFlow</button>
          <button disabled={props.busy} onClick={() => props.onRun("unblock")}><ShieldCheck size={16} />Gỡ chặn</button>
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
