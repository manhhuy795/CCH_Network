const API_BASE = import.meta.env.VITE_API_URL ||
  `${window.location.protocol}//${window.location.hostname}:8000`;

export type Host = {
  name: string;
  label: string;
  ip: string;
  kind: "user" | "service";
  group: string;
  vlan: number | null;
  site: string;
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
  groups: Array<Record<string, unknown>>;
  hosts: Host[];
  links: Link[];
  summary: { user_count: number; service_count: number; controlled_ovs_count: number };
};

export type Decision = {
  action: "allow" | "deny";
  reason: string;
  path: string[];
  blocked_at?: string | null;
};

export type TestResult = {
  ok: boolean;
  message: string;
  decision?: Decision;
  result?: Record<string, number | string | boolean | object | null>;
  raw?: string;
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
  cases: ClusterCase[];
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) throw new Error(`Máy chủ trả về HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

export const api = {
  topology: () => request<Topology>("/api/topology"),
  policies: () => request<Record<string, unknown>>("/api/policies"),
  flows: () => request<{ flows: Array<Record<string, unknown>> }>("/api/flows"),
  status: () => request<Record<string, unknown>>("/api/live/status"),
  post: <T>(path: string, body: object) =>
    request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
};
