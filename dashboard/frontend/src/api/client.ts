const API_BASE = import.meta.env.VITE_API_URL ||
  `${window.location.protocol}//${window.location.hostname}:8000`;
const OPERATOR_TOKEN_KEY = "cch_operator_token";

export type Host = {
  name: string;
  label: string;
  ip: string;
  kind: "user" | "service";
  group: string;
  group_label: string;
  vlan: number | null;
  site: string;
};

export type Group = {
  id: string;
  label: string;
  type: string;
  site: string;
  vlan: number;
  count: number;
  subnet: string;
  switch: string;
  hosts: Host[];
};

export type Link = {
  id: string;
  source: string;
  target: string;
  type: string;
  status: string;
};

export type Topology = {
  nodes: Array<Record<string, unknown>>;
  groups: Group[];
  hosts: Host[];
  links: Link[];
  policy_map: Record<string, { title: string; allow: string[]; deny: string[]; notes: Record<string, string> }>;
  summary: {
    user_count: number;
    service_count: number;
    controlled_ovs_count: number;
    live_link_control?: boolean;
    link_control_message?: string;
  };
};

export type Decision = {
  action: "allow" | "deny";
  reason: string;
  path: string[];
  blocked_at?: string | null;
  failed_link?: string | null;
  enforcement_switch?: string | null;
  policy?: string | null;
  cookie?: string | null;
  priority?: number | null;
  flow_runtime_available?: boolean;
  metadata_source?: string;
};

export type TestResult = {
  ok: boolean;
  message: string;
  error_code?: string | null;
  parse_warning?: string | null;
  cleanup_warning?: string | null;
  decision?: Decision;
  result?: Record<string, number | string | boolean | object | null>;
  raw?: string;
};

export type RealtimeMetric = {
  timestamp: string;
  source: string;
  destination: string;
  ok: boolean;
  delay_ms?: number;
  packet_loss_percent?: number;
  jitter_ms?: number;
  throughput_mbps: number;
  flow_packets: number;
  flow_bytes: number;
  byte_count?: number;
  status: "monitoring" | "idle" | "error";
  message?: string;
};

export type ClusterCase = {
  name: string;
  category: string;
  expected: "allow" | "deny";
  passed: boolean;
  message: string;
  reason?: string;
  rtt_ms?: number;
  jitter_ms?: number;
  loss_percent?: number;
  mos?: number;
  throughput_mbps?: number;
};

export type ClusterDetailResult = {
  ok: boolean;
  cluster: string;
  source: string;
  label: string;
  score: number;
  passed: number;
  total: number;
  message: string;
  verdict: string;
  softphone_note: string;
  voice_estimation_note?: string;
  cases: ClusterCase[];
};

export type AuthStatus = {
  operator_auth_required: boolean;
  operator_token_configured: boolean;
  token_header: string;
  role: string;
};

export function getOperatorToken() {
  return window.localStorage.getItem(OPERATOR_TOKEN_KEY) || "";
}

export function setOperatorToken(token: string) {
  const trimmed = token.trim();
  if (trimmed) window.localStorage.setItem(OPERATOR_TOKEN_KEY, trimmed);
  else window.localStorage.removeItem(OPERATOR_TOKEN_KEY);
}

function authHeaders(): Record<string, string> {
  const token = getOperatorToken();
  return token ? { "X-CCH-Operator-Token": token } : {};
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json();
      detail = typeof payload.detail === "string" ? payload.detail : "";
    } catch {
      detail = "";
    }
    throw new Error(detail || `May chu tra ve HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}


export const api = {
  topology: () => request<Topology>("/api/topology"),
  authStatus: () => request<AuthStatus>("/api/auth/status"),
  policies: () => request<Record<string, unknown>>("/api/policies"),
  flows: () => request<{ flows: Array<Record<string, unknown>> }>("/api/flows"),
  status: () => request<Record<string, unknown>>("/api/live/status"),
  post: <T>(path: string, body: object) =>
    request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
    }),
};

export function wsUrl(source: string, destination: string, interval: number) {
  const base = API_BASE.replace(/^http/, "ws");
  const params = new URLSearchParams({ source, destination, interval: String(interval) });
  return `${base}/ws/metrics?${params.toString()}`;
}
