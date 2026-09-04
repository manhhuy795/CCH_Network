import { expect, test, type Page } from "@playwright/test";
import { installApiMocks, installMockWebSocket, openAuthenticated } from "./mockApi";

async function openTestWorkspace(page: Page, destination = "h90") {
  await page.getByRole("button", { name: "Topology", exact: true }).click();
  await page.getByLabel("Nguồn endpoint").fill("h101_01");
  await page.getByRole("option").filter({ hasText: "h101_01" }).click();
  await page.getByLabel("Đích endpoint").fill(destination);
  await page.getByRole("option").filter({ hasText: destination }).click();
}

test("1. đăng nhập và hiển thị toast accent", async ({ page }) => {
  await installApiMocks(page);
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Xem trước Dashboard" })).toHaveCount(0);
  await expect(page.getByText(/Tài khoản mặc định/)).toHaveCount(0);
  await page.getByLabel("Tên đăng nhập").fill("admin");
  await page.getByLabel("Mật khẩu").fill("CCH@1234");
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  const toast = page.locator(".toast.accent").filter({ hasText: "Phiên admin đã sẵn sàng." });
  await expect(toast).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tổng quan hệ thống" })).toBeVisible();
});

test("2. tổng quan online", async ({ page }) => {
  await openAuthenticated(page);
  await expect(page.getByText("5/5 dịch vụ")).toBeVisible();
});

test("3. backend offline", async ({ page }) => {
  await installApiMocks(page, { backendOffline: true });
  await page.goto("/");
  await page.getByLabel("Tên đăng nhập").fill("admin");
  await page.getByLabel("Mật khẩu").fill("CCH@1234");
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByText(/Không kết nối được FastAPI backend/).first()).toBeVisible();
});

test("4. control agent offline", async ({ page }) => {
  await openAuthenticated(page, { agentOffline: true });
  await expect(page.getByText("4/5 dịch vụ")).toBeVisible();
});

test("5. Ping ALLOW", async ({ page }) => {
  await openAuthenticated(page, { measurement: "ping_allow" });
  await openTestWorkspace(page);
  await page.getByRole("button", { name: /Chạy Ping/ }).click();
  const state = page.getByLabel("Trạng thái phép kiểm tra");
  await expect(state).toContainText("PASS");
  await expect(state).toContainText("REACHABLE");
  await expect(state).toContainText("ALLOW");
  await expect(state).toContainText("OK");
  await expect(page.getByText(/project_1 → access_floor1 → core_hq → fw_hq/)).toBeVisible();
});

test("6. Ping DENY", async ({ page }) => {
  await openAuthenticated(page, { measurement: "ping_deny" });
  await openTestWorkspace(page, "h103_01");
  await page.getByRole("button", { name: /Chạy Ping/ }).click();
  const state = page.getByLabel("Trạng thái phép kiểm tra");
  await expect(state).toContainText("PASS");
  await expect(state).toContainText("DROPPED");
  await expect(state).toContainText("DENY");
  await expect(state).toContainText("OK");
  await expect(page.getByText("POLICY_DENIED")).toBeVisible();
});

test("7. UDP success", async ({ page }) => {
  await openAuthenticated(page, { measurement: "udp_success" });
  await openTestWorkspace(page);
  await page.getByRole("button", { name: "UDP Jitter" }).click();
  await page.getByRole("button", { name: /Chạy UDP Jitter/ }).click();
  await expect(page.getByText("8.5 Mbps")).toBeVisible();
  await expect(page.getByText("1/500")).toBeVisible();
});

test("8. UDP timeout", async ({ page }) => {
  await openAuthenticated(page, { measurement: "udp_timeout" });
  await openTestWorkspace(page);
  await page.getByRole("button", { name: "UDP Jitter" }).click();
  await page.getByRole("button", { name: /Chạy UDP Jitter/ }).click();
  await expect(page.getByRole("alert").getByText("AGENT_TIMEOUT", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Trạng thái phép kiểm tra")).toContainText("ERROR");
  await expect(page.getByLabel("Trạng thái phép kiểm tra")).toContainText("HTTP 504");
});

test("9. UDP BUSY", async ({ page }) => {
  await openAuthenticated(page, { measurement: "udp_busy" });
  await openTestWorkspace(page);
  await page.getByRole("button", { name: "UDP Jitter" }).click();
  await page.getByRole("button", { name: /Chạy UDP Jitter/ }).click();
  await expect(page.getByRole("alert").getByText("IPERF_BUSY", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Trạng thái phép kiểm tra")).toContainText("ERROR");
  await expect(page.getByLabel("Trạng thái phép kiểm tra")).toContainText("HTTP 409");
});

test("10. TCP success", async ({ page }) => {
  await openAuthenticated(page, { measurement: "tcp_success" });
  await openTestWorkspace(page);
  await page.getByRole("button", { name: "TCP Throughput" }).click();
  await page.getByRole("button", { name: /Chạy TCP Throughput/ }).click();
  await expect(page.getByText("95.2 Mbps")).toBeVisible();
  await expect(page.getByText("59500000 bytes")).toBeVisible();
});

test("11. Voice Quality", async ({ page }) => {
  await openAuthenticated(page, { measurement: "voice_success" });
  await openTestWorkspace(page);
  await page.getByRole("button", { name: "Voice Quality" }).click();
  await page.getByRole("button", { name: /Chạy Voice Quality/ }).click();
  await expect(page.getByText("4.3")).toBeVisible();
  await expect(page.getByText(/không phải cuộc gọi SIP\/RTP thật/)).toBeVisible();
});

test("12. policy applying, applied và failed", async ({ page }) => {
  await openAuthenticated(page, { policyResult: "applied", policyDelayMs: 250 });
  await page.getByRole("button", { name: "Chính sách bảo mật" }).click();
  await page.getByRole("article").getByRole("button", { name: "Tắt policy" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Tắt policy" }).click();
  await expect(page.getByText("Applying", { exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByText("Applied", { exact: true })).toBeVisible();

  await page.unrouteAll({ behavior: "wait" });
  await installApiMocks(page, { policyResult: "failed" });
  await page.getByRole("article").getByRole("button", { name: "Tắt policy" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Tắt policy" }).click();
  await expect(page.getByText("Failed")).toBeVisible();
});

test("13. link fail và recover", async ({ page }) => {
  await openAuthenticated(page);
  await page.getByRole("button", { name: "Topology", exact: true }).click();
  await page.getByRole("button", { name: /Ngắt thử nghiệm Primary/ }).first().click();
  await expect(page.getByText("Link đã DOWN.").first()).toBeVisible();
  await page.getByRole("button", { name: /Khôi phục Primary/ }).first().click();
  await expect(page.getByText("Link đã UP.").first()).toBeVisible();
});

test("14. WebSocket tự reconnect", async ({ page }) => {
  await installMockWebSocket(page, true);
  await openAuthenticated(page);
  await page.getByRole("button", { name: "Hiệu năng", exact: true }).click();
  await page.getByRole("combobox", { name: "Nguồn" }).selectOption("h103_01");
  await page.getByRole("combobox", { name: "Đích" }).selectOption("h90");
  await page.getByRole("button", { name: "Bắt đầu" }).click();
  await expect.poll(() => page.evaluate(() => (window as any).__mockSocketCount)).toBeGreaterThanOrEqual(2);
  await expect(page.getByRole("main").getByText("Đang giám sát")).toBeVisible();
});

test("15. đăng nhập không hợp lệ", async ({ page }) => {
  await installApiMocks(page, { verifyInvalid: true });
  await page.goto("/");
  await page.getByLabel("Tên đăng nhập").fill("admin");
  await page.getByLabel("Mật khẩu").fill("wrong-password");
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByText(/Tài khoản hoặc mật khẩu không hợp lệ/).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Đăng nhập hệ thống" })).toBeVisible();
});
