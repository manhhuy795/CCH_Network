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
  bandwidth_mbps?: number;
  delay_ms?: number;
  loss_percent?: number;
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
  session_id?: string;
  duration?: number;
  protocol?: string;
  measurement_completed?: boolean;
  task_id?: string;
  task_status?: "success" | "failed";
  started_at?: string;
  ended_at?: string;
  duration_ms?: number;
  decision?: Decision;
  result?: Record<string, number | string | boolean | object | null>;
  raw?: string;
};

export class ApiClientError extends Error {
  errorCode: string;
  status: number;
  requestId: string;

  constructor(message: string, errorCode = "BACKEND_OFFLINE", status = 0, requestId = "") {
    super(message);
    this.name = "ApiClientError";
    this.errorCode = errorCode;
    this.status = status;
    this.requestId = requestId;
  }
}

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

export type PolicyLifecycleStatus = "Draft" | "Applying" | "Applied" | "Failed" | "Out of sync";

export type PolicyInventoryItem = {
  key: string;
  name: string;
  description: string;
  source: string;
  destination: string;
  action: "ALLOW" | "DROP";
  enforcement_point: string;
  priority: number;
  cookie: string;
  enabled: boolean | null;
  configuration_status: "Enabled" | "Disabled" | "Draft";
  lifecycle_status: PolicyLifecycleStatus;
  controller_acknowledged: boolean;
  updated_at: string;
  technical_detail?: unknown;
};

export type PolicyPayload = {
  metadata?: Record<string, unknown>;
  policies: Record<string, unknown>;
  inventory: PolicyInventoryItem[];
};

export type ActivityEvent = {
  id: string;
  timestamp: string;
  severity: "info" | "warning" | "error";
  component: string;
  event_type: string;
  source?: string | null;
  destination?: string | null;
  message: string;
  technical_detail?: unknown;
  task_id?: string | null;
  error_code?: string | null;
};

export type TaskHistoryItem = {
  task_id: string;
  user_action: string;
  status: "success" | "failed" | "running";
  started_at: string;
  ended_at?: string | null;
  duration_ms?: number | null;
  result_summary?: string | null;
  error_code?: string | null;
  source?: string | null;
  destination?: string | null;
};

export type ActivityPayload = {
  events: ActivityEvent[];
  tasks: TaskHistoryItem[];
  count: number;
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
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new ApiClientError("Đã hủy chờ kết quả trên dashboard.", "TASK_CANCELLED");
    }
    throw new ApiClientError("Không kết nối được FastAPI backend.", "BACKEND_OFFLINE");
  }
  if (!response.ok) {
    let detail = "";
    let errorCode = "";
    let requestId = response.headers.get("X-Request-ID") || "";
    try {
      const payload = await response.json();
      detail = typeof payload.message_vi === "string" ? payload.message_vi :
        (typeof payload.detail === "string" ? payload.detail : "");
      errorCode = typeof payload.error_code === "string" ? payload.error_code : "";
      requestId = typeof payload.request_id === "string" ? payload.request_id : requestId;
    } catch {
      detail = "";
    }
    const suffix = [errorCode, requestId ? `request ${requestId}` : ""].filter(Boolean).join(" · ");
    throw new ApiClientError(
      `${detail || `Máy chủ trả về HTTP ${response.status}`}${suffix ? ` (${suffix})` : ""}`,
      errorCode || `HTTP_${response.status}`,
      response.status,
      requestId,
    );
  }
  return response.json() as Promise<T>;
}


export const api = {
  topology: () => request<Topology>("/api/topology"),
  authStatus: () => request<AuthStatus>("/api/auth/status"),
  policies: () => request<PolicyPayload>("/api/policies"),
  flows: () => request<{ flows: Array<Record<string, unknown>> }>("/api/flows"),
  status: () => request<Record<string, unknown>>("/api/live/status"),
  health: () => request<Record<string, unknown>>("/api/health"),
  activity: () => request<ActivityPayload>("/api/activity"),
  verifyOperator: () => request<{ ok: boolean; authenticated: boolean; role: string }>("/api/auth/verify", {
    headers: authHeaders(),
  }),
  post: <T>(path: string, body: object, signal?: AbortSignal) =>
    request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
      signal,
    }),
};

export function wsUrl(source: string, destination: string, interval: number) {
  const base = API_BASE.replace(/^http/, "ws");
  const params = new URLSearchParams({ source, destination, interval: String(interval) });
  return `${base}/ws/metrics?${params.toString()}`;
}
