import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { openAuthenticated } from "./mockApi";

test("responsive, keyboard và accessibility", async ({ page }) => {
  await openAuthenticated(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => document.activeElement?.tagName);
  expect(focused).not.toBe("BODY");

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((item) => item.impact === "critical" || item.impact === "serious")).toEqual([]);

  await page.getByRole("button", { name: "Topology", exact: true }).click();
  await expect(page.getByTitle("Zoom In")).toBeVisible();
  await expect(page.getByTitle("Zoom Out")).toBeVisible();
});
