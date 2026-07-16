import { ApiClientError, type TestResult } from "../api/client";

export type NetworkTestType = "ping" | "tcp" | "udp" | "quality";

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
