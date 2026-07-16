import { useCallback, useEffect, useRef, useState } from "react";
import { ApiClientError, api, getOperatorToken, setOperatorToken, type AuthStatus, type Decision, type PolicyPayload, type TestResult, type Topology } from "./api/client";
import AppShell, { type DashboardPage } from "./components/layout/AppShell";
import ClusterDetailPanel from "./components/ClusterDetailPanel";
import EventLog, { type LogEntry } from "./components/EventLog";
import FlowTable from "./components/FlowTable";
import MetricsPanel from "./components/MetricsPanel";
import OverviewPage from "./components/OverviewPage";
import PolicyPanel from "./components/PolicyPanel";
import RealtimePanel from "./components/RealtimePanel";
import TestPanel from "./components/TestPanel";
import TopologyCanvas from "./components/TopologyCanvas";
import { ensureTestResult, type NetworkTestType } from "./components/testWorkflow";
import Drawer from "./components/ui/Drawer";
import FeedbackState from "./components/ui/FeedbackState";
import ToastRegion, { type ToastItem } from "./components/ui/ToastRegion";

type Action = NetworkTestType | "simulate" | "block" | "unblock";
type LinkOperation = { linkId: string; action: "fail" | "recover"; status: "running" | "success" | "failed"; message: string };

export default function App() {
  const [page, setPage] = useState<DashboardPage>("overview");
  const [topology, setTopology] = useState<Topology>();
  const [policies, setPolicies] = useState<PolicyPayload>({ policies: {}, inventory: [] });
  const [flows, setFlows] = useState<Array<Record<string, unknown>>>([]);
  const [source, setSource] = useState("h20_01");
  const [destination, setDestination] = useState("h90");
  const [seconds, setSeconds] = useState(5);
  const [testType, setTestType] = useState<NetworkTestType>("ping");
  const [resultType, setResultType] = useState<NetworkTestType>("ping");
  const [busy, setBusy] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [policyBusy, setPolicyBusy] = useState(false);
  const [result, setResult] = useState<TestResult>();
  const [decision, setDecision] = useState<Decision>();
  const [activeIndex, setActiveIndex] = useState(0);
  const [metrics, setMetrics] = useState<Record<string, number | string | boolean | object | null>>({});
  const [events, setEvents] = useState<LogEntry[]>([]);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [failedLinks, setFailedLinks] = useState<string[]>([]);
  const [linkOperation, setLinkOperation] = useState<LinkOperation>();
  const [online, setOnline] = useState(0);
  const [runtime, setRuntime] = useState<Record<string, unknown>>({});
  const [websocketOnline, setWebsocketOnline] = useState(false);
  const [operatorToken, setOperatorTokenState] = useState(getOperatorToken());
  const [authenticated, setAuthenticated] = useState(false);
  const [authChecking, setAuthChecking] = useState(false);
  const [authStatus, setAuthStatus] = useState<AuthStatus>();
  const [helpOpen, setHelpOpen] = useState(false);
  const [lastUpdated, setLastUpdated] = useState("");
  const timer = useRef<number>();
  const taskTimer = useRef<number>();
  const abortController = useRef<AbortController>();
  const actionInFlight = useRef(false);
  const toastSequence = useRef(0);

  const notify = useCallback((message: string, tone: ToastItem["tone"] = "info") => {
    toastSequence.current += 1;
    const id = `${Date.now()}-${toastSequence.current}`;
    setToasts((current) => [...current.slice(-3), { id, message, tone }]);
  }, []);

  const addEvent = useCallback((message: string, kind: LogEntry["kind"] = "info") => {
    setEvents((current) => [
      { time: new Date().toLocaleTimeString("vi-VN"), message, kind },
      ...current,
    ].slice(0, 60));
  }, []);

  const refresh = useCallback(async () => {
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
      const message = error instanceof Error ? error.message : "Không tải được dữ liệu dashboard.";
      addEvent(message, "deny");
      notify(message, "error");
    }
  }, [addEvent, notify]);

  const authenticate = useCallback(async () => {
    if (!operatorToken.trim()) return;
    setAuthChecking(true);
    setOperatorToken(operatorToken);
    try {
      await api.verifyOperator();
      setAuthenticated(true);
      setOperatorTokenState("");
      notify("Đã xác thực phiên IT Operator.", "success");
    } catch (error) {
      setAuthenticated(false);
      setOperatorToken("");
      const message = error instanceof Error ? error.message : "Không xác thực được token.";
      notify(message, "error");
    } finally {
      setAuthChecking(false);
    }
  }, [notify, operatorToken]);

  useEffect(() => {
    void refresh();
    if (getOperatorToken()) {
      setAuthChecking(true);
      api.verifyOperator()
        .then(() => setAuthenticated(true))
        .catch(() => setOperatorToken(""))
        .finally(() => setAuthChecking(false));
    }
    return () => {
      window.clearInterval(timer.current);
      window.clearInterval(taskTimer.current);
      abortController.current?.abort();
    };
  }, [refresh]);

  useEffect(() => {
    window.clearInterval(taskTimer.current);
    if (!busy) return;
    setElapsedSeconds(0);
    const startedAt = Date.now();
    taskTimer.current = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 250);
    return () => window.clearInterval(taskTimer.current);
  }, [busy]);

  const animate = (path: string[]) => {
    window.clearInterval(timer.current);
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setActiveIndex(Math.max(0, path.length - 1));
      return;
    }
    setActiveIndex(0);
    let index = 0;
    timer.current = window.setInterval(() => {
      index += 1;
      setActiveIndex(Math.min(index, path.length - 1));
      if (index >= path.length - 1) window.clearInterval(timer.current);
    }, 450);
  };

  const runAction = async (action: Action) => {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    if (action === "ping" || action === "tcp" || action === "udp" || action === "quality") {
      setResultType(action);
    }
    setBusy(true);
    const controller = new AbortController();
    abortController.current = controller;
    try {
      const pair = { source, destination };
      let rawPayload: unknown;
      if (action === "ping") rawPayload = await api.post("/api/test/ping", pair, controller.signal);
      else if (action === "tcp" || action === "udp") rawPayload = await api.post("/api/test/iperf", { ...pair, protocol: action, seconds }, controller.signal);
      else if (action === "quality") rawPayload = await api.post("/api/test/call-quality", { ...pair, protocol: "udp", seconds }, controller.signal);
      else if (action === "simulate") {
        const simulated = await api.post<Decision & { src: string; dst: string }>("/api/simulate/path", pair);
        rawPayload = { ok: simulated.action === "allow", message: `Mô phỏng ${source} → ${destination}`, decision: simulated, raw: simulated.reason };
      } else rawPayload = await api.post(action === "block" ? "/api/live/block" : "/api/live/unblock", pair, controller.signal);
      const payload = ensureTestResult(rawPayload);

      setResult(payload);
      if (payload.decision) {
        setDecision(payload.decision);
        animate(payload.decision.path);
      }
      if (payload.result) setMetrics(payload.result);
      addEvent(payload.message, payload.ok ? "allow" : "deny");
      notify(payload.message, payload.ok ? "success" : "error");
      const flowData = await api.flows();
      setFlows(flowData.flows);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Thao tác thất bại.";
      const errorCode = error instanceof ApiClientError ? error.errorCode : "UNKNOWN_ERROR";
      setResult({ ok: false, message, error_code: errorCode, raw: message });
      addEvent(message, "deny");
      notify(message, "error");
    } finally {
      abortController.current = undefined;
      actionInFlight.current = false;
      setBusy(false);
    }
  };

  const changeLink = async (linkId: string, fail: boolean) => {
    const action = fail ? "fail" : "recover";
    setLinkOperation({ linkId, action, status: "running", message: fail ? "Đang ngắt liên kết thật trong Mininet." : "Đang khôi phục liên kết thật trong Mininet." });
    try {
      const payload = await api.post<{ ok: boolean; message: string; failed_links: string[] }>(
        fail ? "/api/link/fail" : "/api/link/recover",
        { link_id: linkId },
      );
      setFailedLinks(payload.failed_links);
      setLinkOperation({ linkId, action, status: payload.ok ? "success" : "failed", message: payload.message });
      addEvent(payload.message, payload.ok ? (fail ? "deny" : "allow") : "deny");
      notify(payload.message, payload.ok ? "success" : "error");
      await refresh();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Không thay đổi được trạng thái link.";
      setLinkOperation({ linkId, action, status: "failed", message });
      addEvent(message, "deny");
      notify(message, "error");
    }
  };

  const togglePolicy = async (key: string, enabled: boolean) => {
    setPolicyBusy(true);
    try {
      const payload = await api.post<{ ok: boolean; message: string }>("/api/policy/toggle", { key, enabled });
      addEvent(payload.message, payload.ok ? "allow" : "deny");
      notify(payload.message, payload.ok ? "success" : "error");
      if (payload.ok) await refresh();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Không áp dụng được policy.", "error");
    } finally {
      setPolicyBusy(false);
    }
  };

  const healthComponents = (runtime.components || {}) as Record<string, { status?: string; message_vi?: string }>;
  const overallStatus = String(runtime.status || "unknown");
  const topologyProps = {
    topology,
    links: topology?.links || [],
    decision,
    activeIndex,
    failedLinks,
    liveLinkControl: Boolean(topology?.summary.live_link_control),
    flows,
    metrics,
    linkOperation,
    authenticated,
    source,
    onFail: (id: string) => void changeLink(id, true),
    onRecover: (id: string) => void changeLink(id, false),
    onSource: setSource,
    onDestination: setDestination,
  };

  const pageContent = () => {
    if (!topology && page !== "events") {
      return <FeedbackState kind="loading" title="Đang tải dữ liệu vận hành" message="Dashboard đang đọc topology, health và OpenFlow inventory." />;
    }
    if (page === "topology") return <TopologyCanvas {...topologyProps} />;
    if (page === "testing") return (
      <div className="workspace-grid">
        <TopologyCanvas {...topologyProps} />
        <TestPanel hosts={topology?.hosts || []} source={source} destination={destination} seconds={seconds}
          policyMap={topology?.policy_map} testType={testType} resultType={resultType} busy={busy} elapsedSeconds={elapsedSeconds}
          websocketOnline={websocketOnline} result={result} onSource={setSource} onDestination={setDestination}
          onSeconds={setSeconds} onTestType={setTestType} onRun={(action) => void runAction(action)}
          onCancel={() => abortController.current?.abort()} />
      </div>
    );
    if (page === "policy") return (
      <div className="policy-workspace">
        <div className="main-column"><PolicyPanel policies={policies} onToggle={togglePolicy} busy={policyBusy} /><FlowTable flows={flows} /></div>
        <aside><ClusterDetailPanel /><MetricsPanel metrics={metrics} /></aside>
      </div>
    );
    if (page === "performance") return (
      <div className="performance-grid">
        <RealtimePanel source={source} destination={destination} onStatus={setWebsocketOnline} />
        <MetricsPanel metrics={metrics} />
      </div>
    );
    if (page === "events") return <EventLog entries={events} />;
    return <OverviewPage
      components={healthComponents}
      onlineHosts={online}
      totalHosts={(topology?.summary.user_count ?? 110) + (topology?.summary.service_count ?? 5)}
      failedLinks={failedLinks}
      lastError={events.find((event) => event.kind === "deny")?.message}
      lastUpdated={lastUpdated}
      onNavigate={setPage}
    />;
  };

  return (
    <AppShell
      page={page}
      onPage={setPage}
      overallStatus={overallStatus}
      websocketOnline={websocketOnline}
      authenticated={authenticated}
      authChecking={authChecking}
      token={operatorToken}
      onToken={setOperatorTokenState}
      onAuthenticate={() => void authenticate()}
      onLogout={() => { setOperatorToken(""); setAuthenticated(false); setOperatorTokenState(""); }}
      onHelp={() => setHelpOpen(true)}
    >
      {pageContent()}
      <Drawer open={helpOpen} title="Trợ giúp vận hành" onClose={() => setHelpOpen(false)}>
        <div className="help-content">
          <h3>Trình tự kiểm tra</h3>
          <p>Kiểm tra trạng thái tổng, mở Topology, sau đó chạy phép đo từ một endpoint cụ thể.</p>
          <h3>Kết quả thật</h3>
          <p>Ping và iperf được backend chạy trong namespace Mininet. Packet path lấy từ backend policy decision.</p>
          <h3>Quyền thao tác</h3>
          <p>Link fail/recover, policy toggle và phép đo yêu cầu phiên IT Operator đã xác thực.</p>
          {authStatus && <p>Header xác thực: {authStatus.token_header}</p>}
        </div>
      </Drawer>
      <ToastRegion items={toasts} onDismiss={(id) => setToasts((current) => current.filter((item) => item.id !== id))} />
    </AppShell>
  );
}
