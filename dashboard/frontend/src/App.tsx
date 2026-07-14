import { RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, getOperatorToken, setOperatorToken, type AuthStatus, type Decision, type TestResult, type Topology } from "./api/client";
import ClusterDetailPanel from "./components/ClusterDetailPanel";
import EventLog, { type LogEntry } from "./components/EventLog";
import FlowTable from "./components/FlowTable";
import MetricsPanel from "./components/MetricsPanel";
import PolicyPanel from "./components/PolicyPanel";
import RealtimePanel from "./components/RealtimePanel";
import TestPanel from "./components/TestPanel";
import TopologyCanvas from "./components/TopologyCanvas";

type Action = "ping" | "tcp" | "udp" | "quality" | "simulate" | "block" | "unblock";
type Tab = "overview" | "measure" | "policy" | "logs";

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [topology, setTopology] = useState<Topology>();
  const [policies, setPolicies] = useState<Record<string, unknown>>({});
  const [flows, setFlows] = useState<Array<Record<string, unknown>>>([]);
  const [source, setSource] = useState("h20_01");
  const [destination, setDestination] = useState("h90");
  const [seconds, setSeconds] = useState(5);
  const [busy, setBusy] = useState(false);
  const [policyBusy, setPolicyBusy] = useState(false);
  const [result, setResult] = useState<TestResult>();
  const [decision, setDecision] = useState<Decision>();
  const [activeIndex, setActiveIndex] = useState(0);
  const [metrics, setMetrics] = useState<Record<string, number | string | boolean | object | null>>({});
  const [events, setEvents] = useState<LogEntry[]>([]);
  const [failedLinks, setFailedLinks] = useState<string[]>([]);
  const [online, setOnline] = useState(0);
  const [runtime, setRuntime] = useState<Record<string, unknown>>({});
  const [websocketOnline, setWebsocketOnline] = useState(false);
  const [operatorToken, setOperatorTokenState] = useState(getOperatorToken());
  const [authStatus, setAuthStatus] = useState<AuthStatus>();
  const [lastUpdated, setLastUpdated] = useState("");
  const timer = useRef<number>();

  const addEvent = (message: string, kind: LogEntry["kind"] = "info") => {
    setEvents((current) => [
      { time: new Date().toLocaleTimeString("vi-VN"), message, kind },
      ...current,
    ].slice(0, 60));
  };

  const refresh = async () => {
    try {
      const [topologyData, policyData, flowData, status, auth] = await Promise.all([
        api.topology(), api.policies(), api.flows(), api.status(), api.authStatus(),
      ]);
      setTopology(topologyData);
      setFailedLinks(topologyData.links.filter((link) => link.status === "down").map((link) => link.id));
      setPolicies(policyData);
      setFlows(flowData.flows);
      setRuntime(status);
      setAuthStatus(auth);
      setLastUpdated(new Date().toLocaleString("vi-VN"));
      const hosts = (status.hosts || {}) as Record<string, boolean>;
      setOnline(Object.values(hosts).filter(Boolean).length);
    } catch (error) {
      addEvent(error instanceof Error ? error.message : "Không tải được dữ liệu dashboard.", "deny");
    }
  };

  const saveOperatorToken = (value: string) => {
    setOperatorTokenState(value);
    setOperatorToken(value);
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
      else if (action === "tcp" || action === "udp") payload = await api.post("/api/test/iperf", { ...pair, protocol: action, seconds });
      else if (action === "quality") payload = await api.post("/api/test/call-quality", { ...pair, protocol: "udp", seconds });
      else if (action === "simulate") {
        const simulated = await api.post<Decision & { src: string; dst: string }>("/api/simulate/path", pair);
        payload = { ok: simulated.action === "allow", message: `Mô phỏng ${source} → ${destination}`, decision: simulated, raw: simulated.reason };
      } else payload = await api.post(action === "block" ? "/api/live/block" : "/api/live/unblock", pair);

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
    const payload = await api.post<{ ok: boolean; message: string; failed_links: string[] }>(
      fail ? "/api/link/fail" : "/api/link/recover",
      { link_id: linkId },
    );
    setFailedLinks(payload.failed_links);
    addEvent(payload.message, payload.ok ? (fail ? "deny" : "allow") : "deny");
    await refresh();
  };

  const togglePolicy = async (key: string, enabled: boolean) => {
    setPolicyBusy(true);
    try {
      const payload = await api.post<{ ok: boolean; message: string; policies?: Record<string, unknown> }>("/api/policy/toggle", { key, enabled });
      addEvent(payload.message, payload.ok ? "allow" : "deny");
      if (!payload.ok) return;
      await refresh();
    } catch (error) {
      addEvent(error instanceof Error ? error.message : "Không áp dụng được policy.", "deny");
    } finally {
      setPolicyBusy(false);
    }
  };

  const totalEndpoints = (topology?.summary.user_count ?? 110) + (topology?.summary.service_count ?? 5);
  const switchCount = topology?.summary.controlled_ovs_count ?? 8;
  const tabs: Array<[Tab, string]> = [
    ["overview", "Tong quan"],
    ["measure", "Do kiem mang"],
    ["policy", "Chinh sach & OpenFlow"],
    ["logs", "Nhat ky"],
  ];

  return (
    <main>
      <header>
        <div>
          <h1>Hybrid MPLS L3VPN Logic Simulation + SDN Edge Policy cho Call Center BPO</h1>
          <p>OS-Ken điều khiển Open vSwitch tại SDN Edge; MPLS Logic Cloud chỉ mô phỏng WAN transport giữa HQ và Branch.</p>
        </div>
        <div className="header-actions">
          <label className="token-box">
            <span>IT token</span>
            <input
              value={operatorToken}
              onChange={(event) => saveOperatorToken(event.target.value)}
              placeholder={authStatus?.operator_token_configured ? "Nhap operator token" : "Backend chua cau hinh token"}
              type="password"
            />
          </label>
          <button className="primary" onClick={() => void refresh()}><RefreshCw size={16} />Lam moi</button>
        </div>
      </header>

      <div className="tabs">
        {tabs.map(([key, label]) => <button className={tab === key ? "active" : ""} onClick={() => setTab(key)} key={key}>{label}</button>)}
      </div>

      <div className="summary">
        <div><strong>{online}/{totalEndpoints}</strong><span>Endpoint Mininet</span></div>
        <div><strong>{topology?.summary.user_count ?? 110}</strong><span>User thật</span></div>
        <div><strong>{flows.length}</strong><span>Flow OpenFlow</span></div>
        <div><strong>{websocketOnline ? "Online" : "Idle"}</strong><span>WebSocket</span></div>
      </div>

      {tab === "overview" && (
        <div className="overview-grid">
          <div className="main-column">
            <TopologyCanvas topology={topology} links={topology?.links || []} decision={decision} activeIndex={activeIndex}
              failedLinks={failedLinks} liveLinkControl={Boolean(topology?.summary.live_link_control)}
              source={source} onFail={(id) => void changeLink(id, true)} onRecover={(id) => void changeLink(id, false)}
              onSource={setSource} onDestination={setDestination} />
          </div>
          <aside>
            <section>
              <div className="section-title"><h2>Trang thai he thong</h2><span>{lastUpdated || "Chua cap nhat"}</span></div>
              <div className="metric-grid">
                <div className="metric"><strong>{String(runtime.controller ?? runtime.os_ken ?? "unknown")}</strong><span>OS-Ken</span></div>
                <div className="metric"><strong>{String(runtime.mnexec ?? false)}</strong><span>Mininet</span></div>
                <div className="metric"><strong>{String(runtime.ovs_bridge ?? false)}</strong><span>Open vSwitch</span></div>
                <div className="metric"><strong>{websocketOnline ? "Online" : "Idle"}</strong><span>WebSocket</span></div>
                <div className="metric"><strong>{topology?.summary.user_count ?? 110}</strong><span>User</span></div>
                <div className="metric"><strong>{totalEndpoints}</strong><span>Endpoint</span></div>
                <div className="metric"><strong>{switchCount}</strong><span>Switch OVS</span></div>
                <div className="metric"><strong>{flows.length}</strong><span>OpenFlow flow</span></div>
              </div>
            </section>
            <MetricsPanel metrics={metrics} />
          </aside>
        </div>
      )}

      {tab === "measure" && (
        <div className="operate-grid">
          <div className="main-column">
            <TopologyCanvas topology={topology} links={topology?.links || []} decision={decision} activeIndex={activeIndex}
              failedLinks={failedLinks} liveLinkControl={Boolean(topology?.summary.live_link_control)}
              source={source} onFail={(id) => void changeLink(id, true)} onRecover={(id) => void changeLink(id, false)}
              onSource={setSource} onDestination={setDestination} />
          </div>
          <aside>
            <TestPanel hosts={topology?.hosts || []} source={source} destination={destination} seconds={seconds}
              busy={busy} result={result} onSource={setSource} onDestination={setDestination}
              onSeconds={setSeconds} onRun={(action) => void runAction(action)} />
            <RealtimePanel source={source} destination={destination} onStatus={setWebsocketOnline} />
            <MetricsPanel metrics={metrics} />
            <section>
              <div className="section-title"><h2>Trạng thái runtime</h2><span>Cập nhật từ API</span></div>
              <div className="metric-grid">
                <div className="metric"><strong>{String(runtime.mnexec ?? false)}</strong><span>Mininet/mnexec</span></div>
                <div className="metric"><strong>{String(runtime.ovs_bridge ?? false)}</strong><span>Open vSwitch</span></div>
              </div>
            </section>
          </aside>
        </div>
      )}

      {tab === "policy" && (
        <div className="dashboard-grid">
          <div className="main-column">
            <PolicyPanel policies={policies} onToggle={(key, enabled) => void togglePolicy(key, enabled)} busy={policyBusy} />
            <FlowTable flows={flows} />
          </div>
          <aside>
            <ClusterDetailPanel />
            <MetricsPanel metrics={metrics} />
          </aside>
        </div>
      )}

      {tab === "logs" && <EventLog entries={events} />}
    </main>
  );
}
