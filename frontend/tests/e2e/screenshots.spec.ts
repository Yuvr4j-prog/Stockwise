import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { choosePlanAssumptions, createShop, expectLoadedProductLedger } from "./support";

const views = [
  { name: "desktop", width: 1440, height: 960 },
  { name: "phone", width: 390, height: 844 },
] as const;

async function savePage(page: Page, name: string, view: string) {
  const folder = path.resolve(process.cwd(), "screenshots");
  await mkdir(folder, { recursive: true });
  const viewport = page.viewportSize();
  if (viewport) {
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth), {
      message: `${name}-${view} should keep horizontal scrolling inside its tables`,
    }).toBeLessThanOrEqual(viewport.width);
  }
  await page.screenshot({ path: path.join(folder, `${name}-${view}.png`), fullPage: true, animations: "disabled" });
}

async function openUploadErrors(page: Page) {
  await expectLoadedProductLedger(page);
  await page.getByLabel("Drop a CSV or XLSX file here, or choose a file").setInputFiles({
    name: "preview-errors.csv",
    mimeType: "text/csv",
    buffer: Buffer.from([
      "sku,name,cost_price,profit_per_unit,2026-W46,2026-W47",
      "BAD-1,Invalid Cost,-4,not-a-number,3,5",
      "BAD-2,Bad Week,10,4,1,-2",
    ].join("\n")),
  });
  await page.getByRole("button", { name: "Check upload" }).click();
  await expect(page.locator(".error-summary")).toBeVisible();
}

test("capture all requested pages on desktop and phone using the live API", async ({ page }) => {
  const shop = await createShop(page);
  let planPath = "";
  try {
    for (const view of views) {
      await page.setViewportSize({ width: view.width, height: view.height });

      await page.goto("/login");
      await expect(page.getByRole("heading", { name: "Sign in to the shop ledger", level: 2 })).toBeVisible();
      await savePage(page, "login", view.name);

      await page.goto("/signup");
      await expect(page.getByRole("heading", { name: "Open a shop ledger", level: 2 })).toBeVisible();
      await savePage(page, "signup", view.name);

      await openUploadErrors(page);
      await savePage(page, "products-upload-errors", view.name);

      const product = shop.products.find((row) => row.sku === "RICE-5");
      if (!product) throw new Error("Expected product record was not returned by the live API.");
      await page.goto(`/products/${product.id}`);
      await expect(page.getByRole("heading", { name: "Basmati Rice 5 kg" })).toBeVisible();
      await savePage(page, "product-detail", view.name);

      await page.goto("/plans/new");
      await expect(page.getByRole("heading", { name: "Build a purchase plan", level: 1 })).toBeVisible();
      await choosePlanAssumptions(page);
      await savePage(page, "plan-builder", view.name);

      if (view.name === "desktop") {
        await page.getByRole("button", { name: "Calculate purchase plan" }).click();
        await expect(page).toHaveURL(/\/plans\/\d+$/);
        planPath = new URL(page.url()).pathname;
      } else {
        await page.goto(planPath);
      }
      await expect(page.getByRole("heading", { name: "Purchase recommendation", level: 1 })).toBeVisible();
      await expect(page.getByLabel("Purchase slip")).toBeVisible();
      await savePage(page, "plan-results", view.name);

      await page.goto("/plans");
      await expect(page.getByRole("heading", { name: "Saved purchase plans", level: 1 })).toBeVisible();
      await expect(page.getByText("Basmati Rice 5 kg")).toHaveCount(0);
      await expect(page.getByRole("link", { name: "Open plan" })).toBeVisible();
      await savePage(page, "saved-plans", view.name);

      await page.goto("/settings");
      await expect(page.getByRole("heading", { name: "Ledger settings", level: 1 })).toBeVisible();
      await expect(page.getByRole("region", { name: "Ledger settings" }).getByText(shop.email)).toBeVisible();
      await savePage(page, "settings", view.name);
    }
  } finally {
    await shop.dispose();
  }
});
