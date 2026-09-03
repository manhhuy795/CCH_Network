import type { Page, Route } from "@playwright/test";

type MockOptions = {
  authenticated?: boolean;
  backendOffline?: boolean;
  agentOffline?: boolean;
  verifyInvalid?: boolean;
  measurement?: "ping_allow" | "ping_deny" | "udp_success" | "udp_timeout" | "udp_busy" | "tcp_success" | "voice_success";
  policyResult?: "applied" | "failed";
  policyDelayMs?: number;
};

const hosts = [
  { name: "h101_01", label: "Dự án 1 - User 1", ip: "10.10.101.11", kind: "user", group: "project_1", group_label: "Dự án 1", vlan: 101, site: "hq" },
  { name: "h103_01", label: "Dự án 3 - User 1", ip: "10.10.103.11", kind: "user", group: "project_3", group_label: "Dự án 3", vlan: 103, site: "hq" },
  { name: "h90", label: "Partner PBX", ip: "10.250.10.10", kind: "service", group: "partner", group_label: "Partner services", site: "internet" },
];

const nodes = [
  { id: "c0", label: "OS-Ken", type: "controller" },
  { id: "project_1", label: "Dự án 1", type: "user_group", vlan: 101, count: 20, subnet: "10.10.101.0/24" },
  { id: "project_3", label: "Dự án 3", type: "user_group", vlan: 103, count: 20, subnet: "10.10.103.0/24" },
  { id: "h90", label: "Partner PBX", type: "service", ip: "10.250.10.10" },
  { id: "access_floor1", label: "Access HQ Floor 1", type: "switch", dpid: "1" },
  { id: "access_floor2", label: "Access HQ Floor 2", type: "switch", dpid: "2" },
  { id: "core_hq", label: "Core HQ", type: "switch", dpid: "3" },
  { id: "access_branch", label: "Access Branch", type: "switch", dpid: "4" },
  { id: "dist_branch", label: "Distribution Branch", type: "switch", dpid: "5" },
  { id: "infra_access", label: "Infrastructure Access", type: "switch", dpid: "6" },
  { id: "fw_hq", label: "Firewall HQ", type: "firewall" },
  { id: "fw_telesale", label: "Firewall Branch", type: "firewall" },
  { id: "l2vpn_primary", label: "VLAN 93 L2VPN Primary", type: "l2vpn" },
  { id: "l2vpn_backup", label: "VLAN 93 L2VPN Backup", type: "l2vpn" },
  { id: "ce_hq1", label: "CE-HQ1", type: "ce_bridge", controller_managed: false },
  { id: "ce_hq2", label: "CE-HQ2", type: "ce_bridge", controller_managed: false },
  { id: "ce_branch1", label: "CE-BR1", type: "ce_bridge", controller_managed: false },
  { id: "ce_branch2", label: "CE-BR2", type: "ce_bridge", controller_managed: false },
];

const links = [
  { id: "project_1-access_floor1", source: "project_1", target: "access_floor1", type: "access", status: "up" },
  { id: "access_floor1-core_hq", source: "access_floor1", target: "core_hq", type: "uplink", status: "up" },
  { id: "project_3-access_floor2", source: "project_3", target: "access_floor2", type: "access", status: "up" },
  { id: "access_floor2-core_hq", source: "access_floor2", target: "core_hq", type: "uplink", status: "up" },
  { id: "core_hq-infra_access", source: "core_hq", target: "infra_access", type: "uplink", status: "up" },
  { id: "core_hq-fw_hq", source: "core_hq", target: "fw_hq", type: "routed", status: "up" },
  { id: "fw_hq-h90", source: "fw_hq", target: "h90", type: "service", status: "up" },
  { id: "core_hq-ce_hq1", source: "core_hq", target: "ce_hq1", type: "l2_handoff", status: "up" },
  { id: "ce_hq1-l2vpn_primary", source: "ce_hq1", target: "l2vpn_primary", type: "l2vpn", status: "up" },
  { id: "l2vpn_primary-ce_branch1", source: "l2vpn_primary", target: "ce_branch1", type: "l2vpn", status: "up" },
  { id: "ce_branch1-dist_branch", source: "ce_branch1", target: "dist_branch", type: "l2_handoff", status: "up" },
  { id: "core_hq-ce_hq2", source: "core_hq", target: "ce_hq2", type: "l2_handoff", status: "up" },
  { id: "ce_hq2-l2vpn_backup", source: "ce_hq2", target: "l2vpn_backup", type: "l2vpn", status: "up" },
  { id: "l2vpn_backup-ce_branch2", source: "l2vpn_backup", target: "ce_branch2", type: "l2vpn", status: "up" },
  { id: "ce_branch2-dist_branch", source: "ce_branch2", target: "dist_branch", type: "l2_handoff", status: "up" },
];

const adminUser = { id: "user-admin", username: "admin", role: "admin" as const };

function json(route: Route, payload: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(payload) });
}

function policyItem(lifecycle: "Applied" | "Failed" | "Out of sync" = "Applied") {
  return {
    key: "block_social_media",
    name: "Chặn Social Media",
    description: "Chặn mạng xã hội cho user nghiệp vụ.",
    source: "VLAN 93 / 101 / 103 / 104",
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
    path: ["project_1", "access_floor1", "core_hq", "fw_hq", "h90"],
    enforcement_switch: "core_hq",
    policy: "voice",
    cookie: "0x1200",
    priority: 425,
  };
  if (kind === "ping_deny") return {
    ok: false,
    message: "h101_01 → h103_01: PING THẤT BẠI",
    error_code: "POLICY_DENIED",
    decision: { action: "deny", reason: "Cô lập dự án.", path: ["project_1", "access_floor1", "core_hq"], blocked_at: "core_hq", enforcement_switch: "core_hq", policy: "hq_project_isolation", cookie: "0x1001", priority: 400 },
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
    message: "h101_01 → h90: PING THÀNH CÔNG",
    decision: allowDecision,
    result: { packet_loss_percent: 0, rtt_avg_ms: 8, reachable: true },
  };
}

export async function installApiMocks(page: Page, options: MockOptions = {}) {
  let authenticated = options.authenticated ?? false;
  let policyLifecycle: "Applied" | "Failed" | "Out of sync" = "Applied";
  let failedLinkId = "";
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (options.backendOffline) return route.abort("connectionrefused");
    if (path === "/api/topology") return json(route, {
      nodes,
      groups: [
        { id: "project_1", label: "Dự án 1", type: "user_group", site: "hq", vlan: 101, count: 20, subnet: "10.10.101.0/24", switch: "access_floor1", hosts: [hosts[0]] },
        { id: "project_3", label: "Dự án 3", type: "user_group", site: "hq", vlan: 103, count: 20, subnet: "10.10.103.0/24", switch: "access_floor2", hosts: [hosts[1]] },
      ],
      hosts,
      links: links.map((link) => ({ ...link, status: link.id === failedLinkId ? "down" : "up" })),
      policy_map: {
        project_1: { title: "Dự án 1", allow: ["h90"], deny: ["project_3"], notes: { h90: "Cho phép Voice", project_3: "Cô lập dự án" } },
        project_3: { title: "Dự án 3", allow: ["h90"], deny: ["project_1"], notes: { h90: "Cho phép Voice", project_1: "Cô lập dự án" } },
      },
      summary: { user_count: 90, service_count: 5, controlled_ovs_count: 6, live_link_control: true },
    });
    if (path === "/api/policies") return json(route, { policies: { block_social_media: true }, inventory: [policyItem(policyLifecycle)] });
    if (path === "/api/flows") return json(route, { flows: [{ switch: "core_hq", cookie: "0x1001", priority: 400, match: "h101_01 → h103_01", action: "DROP", packets: 4, bytes: 320, reason: "Cô lập dự án", raw_match: "ip", raw_action: "drop" }] });
    if (path === "/api/live/status") {
      const agentStatus = options.agentOffline ? "offline" : "online";
      return json(route, {
        status: options.agentOffline ? "degraded" : "online",
        hosts: { h101_01: true, h103_01: true, h90: true },
        components: {
          controller: { status: "online", message_vi: "Controller sẵn sàng" },
          backend: { status: "online", message_vi: "Backend sẵn sàng" },
          mininet_topology: { status: "online", message_vi: "Mininet đang chạy" },
          mininet_control_agent: { status: agentStatus, message_vi: options.agentOffline ? "Control Agent offline" : "Control Agent sẵn sàng", error_code: options.agentOffline ? "AGENT_NOT_READY" : null },
          openvswitch: { status: "online", message_vi: "6 OVS online" },
          websocket: { status: "online", message_vi: "WebSocket endpoint sẵn sàng" },
        },
      });
    }
    if (path === "/api/auth/status") return json(route, { session_ttl_seconds: 3600, csrf_header: "X-CSRF-Token", roles: ["admin", "operator", "viewer", "auditor"] });
    if (path === "/api/auth/me") return authenticated
      ? json(route, { ok: true, authenticated: true, user: adminUser })
      : json(route, { error_code: "AUTH_REQUIRED", message_vi: "Cần đăng nhập." }, 401);
    if (path === "/api/auth/login") {
      if (options.verifyInvalid) return json(route, { error_code: "AUTH_INVALID", message_vi: "Tài khoản hoặc mật khẩu không hợp lệ." }, 401);
      authenticated = true;
      return json(route, { ok: true, user: adminUser, expires_at: new Date(Date.now() + 3_600_000).toISOString() });
    }
    if (path === "/api/auth/logout") {
      authenticated = false;
      return json(route, { ok: true, message_vi: "Đã đăng xuất." });
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
      failedLinkId = String((route.request().postDataJSON() as { link_id?: string }).link_id || "");
      return json(route, { ok: true, message: "Link đã DOWN.", failed_links: [failedLinkId] });
    }
    if (path === "/api/link/recover") {
      failedLinkId = "";
      return json(route, { ok: true, message: "Link đã UP.", failed_links: [] });
    }
    if (path === "/api/simulate/path") return json(route, measurementPayload("ping_allow").decision);
    if (path === "/api/live/block" || path === "/api/live/unblock") return json(route, { ok: true, message: "Flow runtime đã cập nhật." });
    return json(route, { ok: true });
  });
}

export async function openAuthenticated(page: Page, options: MockOptions = {}) {
  await installApiMocks(page, { ...options, authenticated: true });
  await page.goto("/");
  await page.getByRole("heading", { name: "Tổng quan hệ thống" }).waitFor();
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
            source: "h101_01",
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
