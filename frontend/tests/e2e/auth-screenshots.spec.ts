import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

test("capture the polished login and signup screens at desktop and phone widths", async ({ page }) => {
  await page.route("**/api/v1/health", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", max_upload_bytes: 4 * 1024 * 1024 }) });
  });
  await page.route("**/api/v1/health/db", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", database: "ok" }) });
  });

  const folder = path.resolve(process.cwd(), "screenshots");
  await mkdir(folder, { recursive: true });
  for (const view of [
    { name: "desktop", width: 1440, height: 960 },
    { name: "phone", width: 390, height: 844 },
  ]) {
    await page.setViewportSize({ width: view.width, height: view.height });
    for (const screen of ["login", "signup"] as const) {
      await page.goto(`/${screen}`);
      const title = screen === "login" ? "Sign in to the shop ledger" : "Open a shop ledger";
      await expect(page.getByRole("heading", { name: title, level: 2 })).toBeVisible();
      await expect(page.getByRole("status")).toHaveCount(0);
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(view.width);
      await page.screenshot({ path: path.join(folder, `${screen}-${view.name}.png`), fullPage: true, animations: "disabled" });
    }
  }
});
