import { RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, type Decision, type TestResult, type Topology } from "./api/client";
import EventLog, { type LogEntry } from "./components/EventLog";
import FlowTable from "./components/FlowTable";
import MetricsPanel from "./components/MetricsPanel";
import PolicyPanel from "./components/PolicyPanel";
import TestPanel from "./components/TestPanel";
import TopologyCanvas from "./components/TopologyCanvas";

type Action = "ping" | "tcp" | "udp" | "quality" | "simulate" | "block" | "unblock";

export default function App() {
  const [topology, setTopology] = useState<Topology>();
  const [policies, setPolicies] = useState<Record<string, unknown>>({});
  const [flows, setFlows] = useState<Array<Record<string, unknown>>>([]);
  const [source, setSource] = useState("h20_01");
  const [destination, setDestination] = useState("h90");
  const [seconds, setSeconds] = useState(5);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<TestResult>();
  const [decision, setDecision] = useState<Decision>();
  const [activeIndex, setActiveIndex] = useState(0);
  const [metrics, setMetrics] = useState<Record<string, number | string | boolean | object | null>>({});
  const [events, setEvents] = useState<LogEntry[]>([]);
  const [failedLinks, setFailedLinks] = useState<string[]>([]);
  const [online, setOnline] = useState(0);
  const timer = useRef<number>();

  const addEvent = (message: string, kind: LogEntry["kind"] = "info") => {
    setEvents((current) => [
      { time: new Date().toLocaleTimeString("vi-VN"), message, kind },
      ...current,
    ].slice(0, 30));
  };

  const refresh = async () => {
    try {
      const [topologyData, policyData, flowData, status] = await Promise.all([
        api.topology(), api.policies(), api.flows(), api.status(),
      ]);
      setTopology(topologyData);
      setPolicies(policyData);
      setFlows(flowData.flows);
      const hosts = (status.hosts || {}) as Record<string, boolean>;
      setOnline(Object.values(hosts).filter(Boolean).length);
    } catch (error) {
      addEvent(error instanceof Error ? error.message : "Không tải được dữ liệu dashboard.", "deny");
    }
  };

  useEffect(() => {
    void refresh();
    return () => window.clearInterval(timer.current);
  }, []);

  const animate = (path: string[]) => {
    window.clearInterval(timer.current);
    setActiveIndex(0);
    let index = 0;
    timer.current = window.setInterval(() => {
      index += 1;
      setActiveIndex(Math.min(index, path.length - 1));
      if (index >= path.length - 1) window.clearInterval(timer.current);
    }, 450);
  };

  const runAction = async (action: Action) => {
    setBusy(true);
    try {
      const pair = { source, destination };
      let payload: TestResult;
      if (action === "ping") payload = await api.post("/api/test/ping", pair);
      else if (action === "tcp" || action === "udp") {
        payload = await api.post("/api/test/iperf", { ...pair, protocol: action, seconds });
      } else if (action === "quality") {
        payload = await api.post("/api/test/call-quality", { ...pair, protocol: "udp", seconds });
      } else if (action === "simulate") {
        const simulated = await api.post<Decision & { src: string; dst: string }>("/api/simulate/path", pair);
        payload = { ok: simulated.action === "allow", message: `Mô phỏng ${source} → ${destination}`, decision: simulated, raw: simulated.reason };
      } else {
        payload = await api.post(action === "block" ? "/api/live/block" : "/api/live/unblock", pair);
      }
      setResult(payload);
      if (payload.decision) {
        setDecision(payload.decision);
        animate(payload.decision.path);
      }
      if (payload.result) setMetrics(payload.result);
      addEvent(payload.message, payload.ok ? "allow" : "deny");
      const flowData = await api.flows();
      setFlows(flowData.flows);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Thao tác thất bại.";
      setResult({ ok: false, message, raw: message });
      addEvent(message, "deny");
    } finally {
      setBusy(false);
    }
  };

  const changeLink = async (linkId: string, fail: boolean) => {
    const payload = await api.post<{ message: string; failed_links: string[] }>(
      fail ? "/api/link/fail" : "/api/link/recover",
      { link_id: linkId },
    );
    setFailedLinks(payload.failed_links);
    addEvent(payload.message, fail ? "deny" : "allow");
  };

  return (
    <main>
      <header>
        <div>
          <h1>Giám sát Hybrid MPLS L3VPN + SDN Call Center CCH</h1>
          <p>SDN điều khiển OVS tại edge; MPLS L3VPN vận chuyển traffic giữa HQ và Branch.</p>
        </div>
        <button className="primary" onClick={() => void refresh()}><RefreshCw size={16} />Làm mới</button>
      </header>

      <div className="summary">
        <div><strong>{online}/105</strong><span>Endpoint Mininet</span></div>
        <div><strong>{topology?.summary.user_count ?? 100}</strong><span>User thật</span></div>
        <div><strong>{topology?.summary.controlled_ovs_count ?? 7}</strong><span>OVS được điều khiển</span></div>
        <div><strong>{flows.length}</strong><span>Flow OpenFlow</span></div>
      </div>

      <div className="dashboard-grid">
        <div className="main-column">
          <TopologyCanvas links={topology?.links || []} decision={decision} activeIndex={activeIndex}
            failedLinks={failedLinks} onFail={(id) => void changeLink(id, true)} onRecover={(id) => void changeLink(id, false)} />
          <FlowTable flows={flows} />
        </div>
        <aside>
          <TestPanel hosts={topology?.hosts || []} source={source} destination={destination} seconds={seconds}
            busy={busy} result={result} onSource={setSource} onDestination={setDestination}
            onSeconds={setSeconds} onRun={(action) => void runAction(action)} />
          <MetricsPanel metrics={metrics} />
          <PolicyPanel policies={policies} />
          <EventLog entries={events} />
        </aside>
      </div>
    </main>
  );
}
