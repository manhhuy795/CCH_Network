import { ClipboardCheck, Loader2 } from "lucide-react";
import { useState } from "react";
import { api, type ClusterDetailResult } from "../api/client";

const clusters = [
  ["project_a", "Dự án A"],
  ["project_b", "Dự án B"],
  ["project_c", "Dự án C"],
  ["telesale", "Telesale"],
  ["backoffice", "BackOffice"],
  ["it_support", "IT Support"],
];

export default function ClusterDetailPanel() {
  const [cluster, setCluster] = useState("project_a");
  const [seconds, setSeconds] = useState(3);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ClusterDetailResult>();

  const runDetail = async () => {
    setBusy(true);
    try {
      const payload = await api.post<ClusterDetailResult>("/api/test/cluster-detail", { cluster, seconds });
      setResult(payload);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <div className="section-title">
        <h2>Test Chi Tiết Theo Cụm</h2>
        <span>Voice estimation, app, Internet, segmentation</span>
      </div>
      <div className="panel-body">
        <div className="form-grid">
          <label>Cụm cần test
            <select value={cluster} onChange={(event) => setCluster(event.target.value)}>
              {clusters.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label>Thời gian đo
            <input type="number" min={1} max={20} value={seconds} onChange={(event) => setSeconds(Number(event.target.value))} />
          </label>
        </div>
        <button className="primary full-button" disabled={busy} onClick={() => void runDetail()}>
          {busy ? <Loader2 size={16} /> : <ClipboardCheck size={16} />}Test chi tiết
        </button>
        {result && (
          <div className={`cluster-result ${result.ok ? "ok" : "bad"}`}>
            <strong>{result.message}</strong>
            <p>{result.voice_estimation_note || result.softphone_note}</p>
            <div className="score-line"><span>Score</span><b>{result.score}%</b><span>{result.passed}/{result.total}</span></div>
            <div className="case-list">
              {result.cases.map((item) => (
                <div className={item.passed ? "case ok" : "case bad"} key={`${item.category}-${item.name}`}>
                  <strong>{item.passed ? "PASS" : "FAIL"} · {item.name}</strong>
                  <span>{item.expected.toUpperCase()} · {item.message}</span>
                  <small>
                    RTT {item.rtt_ms ?? "--"} ms · Jitter {item.jitter_ms ?? "--"} ms · Loss {item.loss_percent ?? "--"}% · MOS {item.mos ?? "--"} · TCP {item.throughput_mbps ?? "--"} Mbps
                  </small>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
