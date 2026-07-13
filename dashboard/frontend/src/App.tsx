import { LogOut, RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, type Decision, type TestResult, type Topology } from "./api/client";
import EventLog, { type LogEntry } from "./components/EventLog";
import FlowTable from "./components/FlowTable";
import MetricsPanel from "./components/MetricsPanel";
import PolicyPanel from "./components/PolicyPanel";
import SecurityDemoPanel from "./components/SecurityDemoPanel";
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
  const [authChecked, setAuthChecked] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [loginToken, setLoginToken] = useState("");
  const [loginError, setLoginError] = useState("");
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
    api.authStatus()
      .then((status) => {
        setAuthenticated(status.ok);
        if (status.ok) void refresh();
      })
      .catch(() => setAuthenticated(false))
      .finally(() => setAuthChecked(true));
    return () => window.clearInterval(timer.current);
  }, []);

  const login = async () => {
    setLoginError("");
    try {
      const payload = await api.login(loginToken);
      if (!payload.ok) {
        setLoginError(payload.message);
        return;
      }
      setAuthenticated(true);
      await refresh();
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : "Không đăng nhập được.");
    }
  };

  const logout = async () => {
    await api.logout().catch(() => undefined);
    setAuthenticated(false);
    setTopology(undefined);
    setFlows([]);
    setOnline(0);
  };

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

  const executeAction = async (action: Action, pairSource: string, pairDestination: string) => {
    setBusy(true);
    try {
      const pair = { source: pairSource, destination: pairDestination };
      let payload: TestResult;
      if (action === "ping") payload = await api.post("/api/test/ping", pair);
      else if (action === "tcp" || action === "udp") {
        payload = await api.post("/api/test/iperf", { ...pair, protocol: action, seconds });
      } else if (action === "quality") {
        payload = await api.post("/api/test/call-quality", { ...pair, protocol: "udp", seconds });
      } else if (action === "simulate") {
        const simulated = await api.post<Decision & { src: string; dst: string }>("/api/simulate/path", pair);
        payload = { ok: simulated.action === "allow", message: `Mô phỏng ${pairSource} → ${pairDestination}`, decision: simulated, raw: simulated.reason };
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

  const runAction = (action: Action) => executeAction(action, source, destination);

  const runScenario = async (scenario: {
    source: string;
    destination: string;
    action: "ping" | "simulate" | "block" | "unblock";
  }) => {
    setSource(scenario.source);
    setDestination(scenario.destination);
    await executeAction(scenario.action, scenario.source, scenario.destination);
  };

  const changeLink = async (linkId: string, fail: boolean) => {
    const payload = await api.post<{ message: string; failed_links: string[] }>(
      fail ? "/api/link/fail" : "/api/link/recover",
      { link_id: linkId },
    );
    setFailedLinks(payload.failed_links);
    addEvent(payload.message, fail ? "deny" : "allow");
  };

  if (!authChecked) {
    return <main><section><div className="panel-body">Đang kiểm tra quyền truy cập dashboard IT...</div></section></main>;
  }

  if (!authenticated) {
    return (
      <main className="login-layout">
        <section className="login-card">
          <div className="section-title"><h2>Dashboard chỉ dành cho IT Support</h2><span>RBAC demo</span></div>
          <div className="panel-body">
            <p>Nhập token phòng IT để xem topology, flow OpenFlow và thực thi các bài kiểm tra bảo mật.</p>
            <label>IT dashboard token
              <input type="password" value={loginToken} onChange={(event) => setLoginToken(event.target.value)}
                onKeyDown={(event) => { if (event.key === "Enter") void login(); }} placeholder="it-support-demo" />
            </label>
            <button className="primary" onClick={() => void login()}><ShieldCheck size={16} />Đăng nhập IT</button>
            {loginError && <div className="result-box bad"><strong>Không đăng nhập được</strong><p>{loginError}</p></div>}
            <div className="explanation">
              <h3>Token lab</h3>
              <p>Mặc định: <strong>it-support-demo</strong>. Có thể đổi bằng biến môi trường <strong>CCH_DASHBOARD_TOKEN</strong>.</p>
            </div>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main>
      <header>
        <div>
          <h1>Giám sát Hybrid MPLS L3VPN + SDN Call Center CCH</h1>
          <p>SDN điều khiển OVS tại edge; MPLS L3VPN vận chuyển traffic giữa HQ và Branch.</p>
        </div>
        <div className="header-actions">
          <button className="primary" onClick={() => void refresh()}><RefreshCw size={16} />Làm mới</button>
          <button onClick={() => void logout()}><LogOut size={16} />Đăng xuất IT</button>
        </div>
      </header>

      <div className="summary">
        <div><strong>{online}/{(topology?.summary.user_count ?? 104) + (topology?.summary.service_count ?? 5)}</strong><span>Endpoint Mininet</span></div>
        <div><strong>{topology?.summary.user_count ?? 104}</strong><span>User thật</span></div>
        <div><strong>{topology?.summary.controlled_ovs_count ?? 8}</strong><span>OVS được điều khiển</span></div>
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
          <SecurityDemoPanel busy={busy} onRun={(scenario) => void runScenario(scenario)} />
          <MetricsPanel metrics={metrics} />
          <PolicyPanel policies={policies} />
          <EventLog entries={events} />
        </aside>
      </div>
    </main>
  );
}
