import { ApiClientError, type TestResult } from "../api/client";

export type NetworkTestType = "ping" | "tcp" | "udp" | "quality";

export type TestCaseStatus = "PASS" | "FAIL" | "ERROR";
export type NetworkResultStatus = "REACHABLE" | "DROPPED" | "NOT OBSERVED";
export type ExpectedPolicyStatus = "ALLOW" | "DENY" | "UNKNOWN";

export type TestSemanticState = {
  testCase: TestCaseStatus;
  actualNetwork: NetworkResultStatus;
  expectedPolicy: ExpectedPolicyStatus;
  backendApi: string;
  backendOk: boolean;
};

export const testLabels: Record<NetworkTestType, string> = {
  ping: "Ping",
  tcp: "TCP Throughput",
  udp: "UDP Jitter",
  quality: "Voice Quality",
};

const guidance: Record<string, string> = {
  MININET_NOT_RUNNING: "Khởi động topology Mininet ở Terminal 1 rồi thử lại.",
  AGENT_NOT_READY: "Control Agent chưa sẵn sàng. Kiểm tra terminal topology và socket runtime.",
  AGENT_DISCONNECTED: "Control Agent đã mất kết nối. Kiểm tra topology có còn chạy hay không.",
  AGENT_TIMEOUT: "Agent vẫn có thể đang xử lý. Kiểm tra health và log trước khi chạy lại.",
  IPERF_BUSY: "Đích đang có phiên iperf khác. Chờ phiên hiện tại kết thúc rồi retry.",
  POLICY_DENIED: "Policy đang chặn luồng này. Xem enforcement point và reason, không mở server iperf.",
  BACKEND_OFFLINE: "FastAPI backend không phản hồi. Kiểm tra port 8000 và logs/backend.log.",
  AUTH_REQUIRED: "Nhập IT operator token trên header.",
  AUTH_INVALID: "Token không hợp lệ. Đọc lại logs/operator.token trên Ubuntu.",
  TASK_CANCELLED: "Dashboard đã ngừng chờ. Tác vụ backend có thể cần hoàn tất cleanup.",
  MALFORMED_RESPONSE: "Backend trả dữ liệu thiếu contract. Lưu request ID và kiểm tra backend log.",
  WEBSOCKET_OFFLINE: "WebSocket metrics đang mất kết nối. Phép đo chủ động vẫn dùng API HTTP.",
};

export function errorGuidance(errorCode?: string | null) {
  return guidance[errorCode || ""] || "Xem error code, request ID và backend log để xác định thành phần lỗi.";
}

export function ensureTestResult(value: unknown): TestResult {
  if (!value || typeof value !== "object" || typeof (value as TestResult).ok !== "boolean") {
    throw new ApiClientError("Backend trả response không đúng contract phép đo.", "MALFORMED_RESPONSE");
  }
  return value as TestResult;
}

export function deriveTestSemanticState(result: TestResult, expectedAllow?: boolean): TestSemanticState {
  const expectedPolicy: ExpectedPolicyStatus = expectedAllow === true
    ? "ALLOW"
    : expectedAllow === false
      ? "DENY"
      : result.decision?.action === "allow"
        ? "ALLOW"
        : result.decision?.action === "deny"
          ? "DENY"
          : "UNKNOWN";
  const backendOk = !result.http_status && !result.error_code;
  const measuredReachable = result.result?.reachable;
  const actualNetwork: NetworkResultStatus = !backendOk && result.error_code !== "POLICY_DENIED"
    ? "NOT OBSERVED"
    : typeof measuredReachable === "boolean"
      ? measuredReachable ? "REACHABLE" : "DROPPED"
      : result.error_code === "POLICY_DENIED"
      ? "DROPPED"
      : result.ok || result.measurement_completed
        ? "REACHABLE"
        : "DROPPED";
  const matchesPolicy = (expectedPolicy === "ALLOW" && actualNetwork === "REACHABLE")
    || (expectedPolicy === "DENY" && actualNetwork === "DROPPED");
  const testCase: TestCaseStatus = !backendOk && result.error_code !== "POLICY_DENIED"
    ? "ERROR"
    : matchesPolicy && (expectedPolicy === "DENY" || result.ok)
      ? "PASS"
      : "FAIL";

  return {
    testCase,
    actualNetwork,
    expectedPolicy,
    backendApi: result.http_status ? `HTTP ${result.http_status}` : backendOk || result.error_code === "POLICY_DENIED" ? "OK" : "UNAVAILABLE",
    backendOk: backendOk || result.error_code === "POLICY_DENIED",
  };
}
