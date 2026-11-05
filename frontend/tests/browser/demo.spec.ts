import { expect, test } from "@playwright/test";

test("both scenarios execute through the API and reset without a refresh", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Run demonstration" })).toBeEnabled();
  await page.getByRole("button", { name: "Run demonstration" }).click();
  await expect(page.getByText("Consistent state. Valid work preserved.")).toBeVisible();
  await expect(page.getByText("Stream complete")).toBeVisible();
  await expect(page.getByText("non disruptive", { exact: true })).toBeVisible();
  await expect(page.getByText("Rebase", { exact: true })).toBeVisible();
  await expect(page.getByText("Version conflict detected", { exact: true })).toBeVisible();
  await expect(page.getByText("No reasoning nodes invalidated.", { exact: false })).toBeVisible();
  const final = page.locator(".final-state");
  await expect(final).toContainText("60"); await expect(final).toContainText("$25");
  await page.screenshot({ path: "test-results/non-disruptive-desktop.png", fullPage: true });
  await page.getByRole("button", { name: "Reset workspace" }).click();
  await expect(page.getByText("Final state awaits verification")).toBeVisible();
  await page.getByRole("button", { name: /Inventory allocation/ }).click();
  await page.getByRole("button", { name: "Run demonstration" }).click();
  await expect(page.getByText("Stream complete")).toBeVisible();
  await expect(page.getByText("Selective re-execution", { exact: true })).toBeVisible();
  await expect(page.getByText("recover_a_reason", { exact: true })).toBeVisible();
  await expect(final).toContainText("30"); await expect(final).toContainText("$20");
  await page.screenshot({ path: "test-results/disruptive-desktop.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("mobile layout stays within the viewport and completes", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Run demonstration" })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/idle-mobile.png", fullPage: true });
  await page.getByRole("button", { name: /Inventory allocation/ }).click();
  await page.getByRole("button", { name: "Run demonstration" }).click();
  await expect(page.getByText("Stream complete")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/disruptive-mobile.png", fullPage: true });
});

test("API unavailability has a working retry and failed commands can reset", async ({ page }) => {
  await page.route("**/api/demo/scenarios", route => route.abort());
  await page.goto("/");
  await expect(page.getByText("Demo API is unavailable")).toBeVisible();
  await expect(page.getByRole("button", { name: "Run demonstration" })).toBeDisabled();
  await page.unroute("**/api/demo/scenarios");
  await page.getByRole("button", { name: "Retry connection" }).click();
  await expect(page.getByRole("button", { name: "Run demonstration" })).toBeEnabled();
  await page.route("**/api/demo/run", route => route.abort());
  await page.getByRole("button", { name: "Run demonstration" }).click();
  await expect(page.getByText("Demo failed", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Reset workspace" }).click();
  await expect(page.getByText("Final state awaits verification")).toBeVisible();
  await expect(page.getByText("Demo failed", { exact: true })).not.toBeVisible();
});
