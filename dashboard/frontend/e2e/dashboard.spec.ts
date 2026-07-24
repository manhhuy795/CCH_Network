import { expect, test } from "@playwright/test";
import { installApiMocks, installMockWebSocket, openAuthenticated } from "./mockApi";

test("1. login bằng operator token", async ({ page }) => {
  await installApiMocks(page);
  await page.goto("/");
  await page.getByLabel("IT operator token").fill("valid-token");
  await page.getByRole("button", { name: "Xác thực" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Đã xác thực" })).toBeVisible();
  await expect(page.getByLabel("IT operator token")).toHaveCount(0);
});

test("2. tổng quan online", async ({ page }) => {
  await openAuthenticated(page);
  await expect(page.getByText("Controller sẵn sàng")).toBeVisible();
  await expect(page.getByText("3/3")).toBeVisible();
});

test("3. backend offline", async ({ page }) => {
  await installApiMocks(page, { backendOffline: true });
  await page.goto("/");
  await expect(page.getByText(/Không kết nối được FastAPI backend/).first()).toBeVisible();
});

test("4. control agent offline", async ({ page }) => {
  await openAuthenticated(page, { agentOffline: true });
  await expect(page.getByText("Control Agent offline")).toBeVisible();
  await expect(page.getByText("AGENT_NOT_READY")).toBeVisible();
});

test("5. Ping ALLOW", async ({ page }) => {
  await openAuthenticated(page, { measurement: "ping_allow" });
  await page.getByRole("button", { name: "Kiểm tra kết nối" }).first().click();
  await page.getByRole("button", { name: /Chạy Ping/ }).click();
  await expect(page.locator(".test-result .result-heading strong")).toContainText("PING THÀNH CÔNG");
  await expect(page.getByText(/project_b → access_floor1 → dist_hq_1 → core_hq/)).toBeVisible();
});

test("6. Ping DENY", async ({ page }) => {
  await openAuthenticated(page, { measurement: "ping_deny" });
  await page.getByRole("button", { name: "Kiểm tra kết nối" }).first().click();
  await page.getByRole("button", { name: /Chạy Ping/ }).click();
  await expect(page.getByText("Policy DENY")).toBeVisible();
  await expect(page.getByText("POLICY_DENIED")).toBeVisible();
});

test("7. UDP success", async ({ page }) => {
  await openAuthenticated(page, { measurement: "udp_success" });
  await page.getByRole("button", { name: "Kiểm tra kết nối" }).first().click();
  await page.getByRole("button", { name: "UDP Jitter" }).click();
  await page.getByRole("button", { name: /Chạy UDP Jitter/ }).click();
  await expect(page.getByText("8.5 Mbps")).toBeVisible();
  await expect(page.getByText("1/500")).toBeVisible();
});

test("8. UDP timeout", async ({ page }) => {
  await openAuthenticated(page, { measurement: "udp_timeout" });
  await page.getByRole("button", { name: "Kiểm tra kết nối" }).first().click();
  await page.getByRole("button", { name: "UDP Jitter" }).click();
  await page.getByRole("button", { name: /Chạy UDP Jitter/ }).click();
  await expect(page.getByRole("alert").getByText("AGENT_TIMEOUT", { exact: true })).toBeVisible();
});

test("9. UDP BUSY", async ({ page }) => {
  await openAuthenticated(page, { measurement: "udp_busy" });
  await page.getByRole("button", { name: "Kiểm tra kết nối" }).first().click();
  await page.getByRole("button", { name: "UDP Jitter" }).click();
  await page.getByRole("button", { name: /Chạy UDP Jitter/ }).click();
  await expect(page.getByRole("alert").getByText("IPERF_BUSY", { exact: true })).toBeVisible();
});

test("10. TCP success", async ({ page }) => {
  await openAuthenticated(page, { measurement: "tcp_success" });
  await page.getByRole("button", { name: "Kiểm tra kết nối" }).first().click();
  await page.getByRole("button", { name: "TCP Throughput" }).click();
  await page.getByRole("button", { name: /Chạy TCP Throughput/ }).click();
  await expect(page.getByText("95.2 Mbps")).toBeVisible();
  await expect(page.getByText("59500000 bytes")).toBeVisible();
});

test("11. Voice Quality", async ({ page }) => {
  await openAuthenticated(page, { measurement: "voice_success" });
  await page.getByRole("button", { name: "Kiểm tra kết nối" }).first().click();
  await page.getByRole("button", { name: "Voice Quality" }).click();
  await page.getByRole("button", { name: /Chạy Voice Quality/ }).click();
  await expect(page.getByText("4.3")).toBeVisible();
  await expect(page.getByText(/không phải cuộc gọi SIP\/RTP thật/)).toBeVisible();
});

test("12. policy applying, applied và failed", async ({ page }) => {
  await openAuthenticated(page, { policyResult: "applied", policyDelayMs: 250 });
  await page.getByRole("button", { name: "Chính sách & OpenFlow" }).click();
  await page.getByRole("article").getByRole("button", { name: "Tắt policy" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Tắt policy" }).click();
  await expect(page.getByText("Applying")).toBeVisible();
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
  await page.getByLabel("Link project_a đến access_floor1").click();
  await page.getByRole("button", { name: "Fail link" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Fail link" }).click();
  await expect(page.getByText("Thành công")).toBeVisible();
  await page.getByRole("button", { name: "Recover" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Recover link" }).click();
  await expect(page.getByLabel(/Link · project_a/).getByText("Link đã UP.")).toBeVisible();
});

test("14. WebSocket tự reconnect", async ({ page }) => {
  await installMockWebSocket(page, true);
  await openAuthenticated(page);
  await page.getByRole("button", { name: "Hiệu năng" }).click();
  await page.getByRole("button", { name: "Bắt đầu" }).click();
  await expect.poll(() => page.evaluate(() => (window as any).__mockSocketCount)).toBeGreaterThanOrEqual(2);
  await expect(page.getByRole("main").getByText("WebSocket online")).toBeVisible();
});

test("15. token invalid", async ({ page }) => {
  await installApiMocks(page, { verifyInvalid: true });
  await page.goto("/");
  await page.getByLabel("IT operator token").fill("wrong-token");
  await page.getByRole("button", { name: "Xác thực" }).click();
  await expect(page.getByText(/Token không hợp lệ/)).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Đã xác thực" })).toHaveCount(0);
});
