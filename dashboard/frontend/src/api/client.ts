const API_BASE = import.meta.env.VITE_API_URL ||
  `${window.location.protocol}//${window.location.hostname}:8000`;
const TOKEN_KEY = "cch_it_dashboard_token";

export function dashboardToken() {
  return window.localStorage.getItem(TOKEN_KEY) || "";
}

export function setDashboardToken(token: string) {
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

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

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  const token = dashboardToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (response.status === 401) {
    setDashboardToken("");
    throw new Error("Dashboard chỉ dành cho IT Support. Hãy đăng nhập lại.");
  }
  if (!response.ok) throw new Error(`Máy chủ trả về HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

export const api = {
  login: async (token: string) => {
    const response = await request<{ ok: boolean; message: string }>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    if (response.ok) setDashboardToken(token);
    return response;
  },
  logout: async () => {
    const response = await request<{ ok: boolean; message: string }>("/auth/logout", { method: "POST" });
    setDashboardToken("");
    return response;
  },
  authStatus: () => request<{ ok: boolean; role: string | null }>("/auth/status"),
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
