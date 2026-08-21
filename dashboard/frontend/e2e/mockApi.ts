import type { Page, Route } from "@playwright/test";

type MockOptions = {
  backendOffline?: boolean;
  agentOffline?: boolean;
  verifyInvalid?: boolean;
  measurement?: "ping_allow" | "ping_deny" | "udp_success" | "udp_timeout" | "udp_busy" | "tcp_success" | "voice_success";
  policyResult?: "applied" | "failed";
  policyDelayMs?: number;
};

const hosts = [
  { name: "h20_01", label: "Dự án A - User 1", ip: "172.10.20.11", kind: "user", group: "project_a", group_label: "Dự án A", vlan: 20, site: "HQ" },
  { name: "h30_01", label: "Dự án B - User 1", ip: "172.10.30.11", kind: "user", group: "project_b", group_label: "Dự án B", vlan: 30, site: "HQ" },
  { name: "h90", label: "Voice Service", ip: "172.10.90.10", kind: "service", group: "h90", group_label: "Voice", vlan: 90, site: "HQ" },
];

const nodes = [
  { id: "c0", label: "OS-Ken", type: "controller" },
  { id: "project_a", label: "Dự án A", type: "user_group", vlan: 20, count: 1, subnet: "172.10.20.0/24" },
  { id: "project_b", label: "Dự án B", type: "user_group", vlan: 30, count: 1, subnet: "172.10.30.0/24" },
  { id: "h90", label: "Voice Service", type: "service", ip: "172.10.90.10" },
  { id: "access_floor1", label: "Access HQ Floor 1", type: "switch", dpid: "1" },
  { id: "access_floor2", label: "Access HQ Floor 2", type: "switch", dpid: "2" },
  { id: "dist_hq_1", label: "Distribution HQ 1", type: "switch", dpid: "3" },
  { id: "dist_hq_2", label: "Distribution HQ 2", type: "switch", dpid: "4" },
  { id: "core_hq", label: "Core HQ", type: "switch", dpid: "5" },
  { id: "access_branch", label: "Access Branch", type: "switch", dpid: "6" },
  { id: "dist_branch", label: "Distribution Branch", type: "switch", dpid: "7" },
  { id: "infra_access", label: "Infrastructure Access", type: "switch", dpid: "8" },
];

const links = [
  { id: "project_a-access_floor1", source: "project_a", target: "access_floor1", type: "access", status: "up" },
  { id: "access_floor1-dist_hq_1", source: "access_floor1", target: "dist_hq_1", type: "uplink", status: "up" },
  { id: "project_b-access_floor2", source: "project_b", target: "access_floor2", type: "access", status: "up" },
  { id: "access_floor2-dist_hq_2", source: "access_floor2", target: "dist_hq_2", type: "uplink", status: "up" },
  { id: "dist_hq_1-core_hq", source: "dist_hq_1", target: "core_hq", type: "uplink", status: "up" },
  { id: "core_hq-infra_access", source: "core_hq", target: "infra_access", type: "uplink", status: "up" },
  { id: "infra_access-h90", source: "infra_access", target: "h90", type: "access", status: "up" },
];

function json(route: Route, payload: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
}

function policyItem(lifecycle: "Applied" | "Failed" | "Out of sync" = "Applied") {
  return {
    key: "block_social_media",
    name: "Chặn Social Media",
    description: "Chặn mạng xã hội cho user nghiệp vụ.",
    source: "VLAN 20 / 30 / 40",
    destination: "hsocial",
    action: "DROP",
    enforcement_point: "core_hq",
    priority: 470,
    cookie: "0x1304",
    enabled: true,
    configuration_status: "Enabled",
    lifecycle_status: lifecycle,
    controller_acknowledged: lifecycle === "Applied",
    updated_at: new Date().toISOString(),
  };
}

function measurementPayload(kind: MockOptions["measurement"]) {
  const allowDecision = {
    action: "allow",
    reason: "Voice được policy cho phép.",
    path: ["project_b", "access_floor1", "dist_hq_1", "core_hq", "infra_access", "h90"],
    enforcement_switch: "core_hq",
    policy: "voice",
    cookie: "0x1200",
    priority: 425,
  };
  if (kind === "ping_deny") return {
    ok: false,
    message: "h20_01 → h30_01: PING THẤT BẠI",
    error_code: "POLICY_DENIED",
    decision: { action: "deny", reason: "Cô lập dự án.", path: ["project_a", "access_floor1", "dist_hq_1", "core_hq"], blocked_at: "core_hq", enforcement_switch: "core_hq", policy: "hq_project_isolation", cookie: "0x1001", priority: 400 },
    result: { packet_loss_percent: 100, reachable: false },
  };
  if (kind === "udp_timeout") return { ok: false, message: "Agent timeout", error_code: "AGENT_TIMEOUT" };
  if (kind === "udp_busy") return { ok: false, message: "Đích đang có phiên iperf khác", error_code: "IPERF_BUSY" };
  if (kind === "udp_success") return {
    ok: true, message: "UDP hoàn tất", session_id: "udp-e2e", duration: 5, decision: allowDecision,
    result: { throughput_mbps: 8.5, jitter_ms: 1.4, packet_loss_percent: 0.2, lost_packets: 1, total_datagrams: 500 },
  };
  if (kind === "tcp_success") return {
    ok: true, message: "TCP hoàn tất", session_id: "tcp-e2e", duration: 5, decision: allowDecision,
    result: { throughput_mbps: 95.2, transferred_bytes: 59_500_000 },
  };
  if (kind === "voice_success") return {
    ok: true, message: "Voice Quality hoàn tất", decision: allowDecision,
    result: { rtt_avg_ms: 28, jitter_ms: 2, packet_loss_percent: 0, mos: 4.3, r_factor: 91, rating: "Tốt" },
  };
  return {
    ok: true,
    message: "h30_01 → h90: PING THÀNH CÔNG",
    decision: allowDecision,
    result: { packet_loss_percent: 0, rtt_avg_ms: 8, reachable: true },
  };
}

export async function installApiMocks(page: Page, options: MockOptions = {}) {
  let policyLifecycle: "Applied" | "Failed" | "Out of sync" = "Applied";
  let linkDown = false;
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (options.backendOffline) return route.abort("connectionrefused");
    if (path === "/api/topology") return json(route, {
      nodes,
      groups: [
        { id: "project_a", label: "Dự án A", type: "user_group", site: "HQ", vlan: 20, count: 1, subnet: "172.10.20.0/24", switch: "access_floor1", hosts: [hosts[0]] },
        { id: "project_b", label: "Dự án B", type: "user_group", site: "HQ", vlan: 30, count: 1, subnet: "172.10.30.0/24", switch: "access_floor1", hosts: [hosts[1]] },
      ],
      hosts,
      links: links.map((link) => link.id === "project_a-access_floor1" ? { ...link, status: linkDown ? "down" : "up" } : link),
      policy_map: {
        project_a: { title: "Dự án A", allow: ["h90"], deny: ["project_b"], notes: { h90: "Cho phép Voice", project_b: "Cô lập dự án" } },
        project_b: { title: "Dự án B", allow: ["h90"], deny: ["project_a"], notes: { h90: "Cho phép Voice", project_a: "Cô lập dự án" } },
      },
      summary: { user_count: 2, service_count: 1, controlled_ovs_count: 8, live_link_control: true },
    });
    if (path === "/api/policies") return json(route, { policies: { block_social_media: true }, inventory: [policyItem(policyLifecycle)] });
    if (path === "/api/flows") return json(route, { flows: [{ switch: "core_hq", cookie: "0x1001", priority: 400, match: "h20_01 → h30_01", action: "DROP", packets: 4, bytes: 320, reason: "Cô lập dự án", raw_match: "ip", raw_action: "drop" }] });
    if (path === "/api/live/status") {
      const agentStatus = options.agentOffline ? "offline" : "online";
      return json(route, {
        status: options.agentOffline ? "degraded" : "online",
        hosts: { h20_01: true, h30_01: true, h90: true },
        components: {
          controller: { status: "online", message_vi: "Controller sẵn sàng" },
          backend: { status: "online", message_vi: "Backend sẵn sàng" },
          mininet_topology: { status: "online", message_vi: "Mininet đang chạy" },
          mininet_control_agent: { status: agentStatus, message_vi: options.agentOffline ? "Control Agent offline" : "Control Agent sẵn sàng", error_code: options.agentOffline ? "AGENT_NOT_READY" : null },
          openvswitch: { status: "online", message_vi: "8 OVS online" },
          websocket: { status: "online", message_vi: "WebSocket endpoint sẵn sàng" },
        },
      });
    }
    if (path === "/api/auth/status") return json(route, { operator_auth_required: true, operator_token_configured: true, token_header: "X-CCH-Operator-Token", role: "it_operator" });
    if (path === "/api/auth/verify") {
      if (options.verifyInvalid) return json(route, { ok: false, error_code: "AUTH_INVALID", message_vi: "Token không hợp lệ." }, 403);
      return json(route, { ok: true, authenticated: true, role: "it_operator" });
    }
    if (path === "/api/activity") return json(route, { events: [], tasks: [], count: 0 });
    if (path === "/api/health") return json(route, { status: "online" });
    if (path === "/api/test/ping" || path === "/api/test/iperf" || path === "/api/test/call-quality") {
      const payload = measurementPayload(options.measurement);
      const status = payload.error_code === "AGENT_TIMEOUT" ? 504 : payload.error_code === "IPERF_BUSY" ? 409 : 200;
      return json(route, payload, status);
    }
    if (path === "/api/policy/toggle") {
      policyLifecycle = options.policyResult === "failed" ? "Failed" : "Applied";
      if (options.policyDelayMs) await new Promise((resolve) => setTimeout(resolve, options.policyDelayMs));
      return json(route, { ok: policyLifecycle === "Applied", message: policyLifecycle === "Applied" ? "Policy đã áp dụng." : "Policy reload thất bại.", status: policyLifecycle });
    }
    if (path === "/api/link/fail") {
      linkDown = true;
      return json(route, { ok: true, message: "Link đã DOWN.", failed_links: ["project_a-access_floor1"] });
    }
    if (path === "/api/link/recover") {
      linkDown = false;
      return json(route, { ok: true, message: "Link đã UP.", failed_links: [] });
    }
    if (path === "/api/simulate/path") return json(route, measurementPayload("ping_allow").decision);
    if (path === "/api/live/block" || path === "/api/live/unblock") return json(route, { ok: true, message: "Flow runtime đã cập nhật." });
    return json(route, { ok: true });
  });
}

export async function openAuthenticated(page: Page, options: MockOptions = {}) {
  await page.addInitScript(() => window.localStorage.setItem("cch_operator_token", "mock-operator-token"));
  await installApiMocks(page, options);
  await page.goto("/");
  await page.getByText("Tổng quan vận hành").waitFor();
}

export async function installMockWebSocket(page: Page, closeFirst = false) {
  await page.addInitScript(({ shouldCloseFirst }) => {
    class BrowserMockWebSocket {
      static count = 0;
      onopen: (() => void) | null = null;
      onclose: (() => void) | null = null;
      onerror: (() => void) | null = null;
      onmessage: ((event: { data: string }) => void) | null = null;
      closed = false;

      constructor(_url: string) {
        BrowserMockWebSocket.count += 1;
        (window as any).__mockSocketCount = BrowserMockWebSocket.count;
        window.setTimeout(() => {
          if (this.closed) return;
          this.onopen?.();
          this.onmessage?.({ data: JSON.stringify({
            timestamp: new Date().toISOString(),
            source: "h30_01",
            destination: "h90",
            ok: true,
            delay_ms: 8,
            packet_loss_percent: 0,
            jitter_ms: 1,
            throughput_mbps: 0.2,
            flow_packets: 12,
            flow_bytes: 1200,
            status: "monitoring",
          }) });
          if (shouldCloseFirst && BrowserMockWebSocket.count === 1) window.setTimeout(() => this.onclose?.(), 50);
        }, 10);
      }

      close() {
        this.closed = true;
      }
    }
    (window as any).WebSocket = BrowserMockWebSocket;
  }, { shouldCloseFirst: closeFirst });
}
