import { expect, test } from "@playwright/test";
import { createShop, expectLoadedProductLedger } from "./support";

test("upload preview reports row-level CSV errors before commit", async ({ page }) => {
  const shop = await createShop(page);
  try {
    await expectLoadedProductLedger(page);
    const invalidCsv = [
      "sku,name,cost_price,profit_per_unit,2026-W46,2026-W47",
      "BAD-1,Invalid Cost,-4,not-a-number,3,5",
      "BAD-2,Bad Week,10,4,1,-2",
      "BAD-2,Duplicate SKU,10,4,1,2",
    ].join("\n");
    await page.getByLabel("Drop a CSV or XLSX file here, or choose a file").setInputFiles({
      name: "invalid-sales.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(invalidCsv),
    });
    await page.getByRole("button", { name: "Check upload" }).click();
    const previewErrors = page.locator(".error-summary");
    await expect(previewErrors).toBeVisible();
    await expect(previewErrors).toContainText("Fix these rows before saving the upload.");
    await expect(previewErrors.locator("li")).toHaveCount(4);
    await expect(previewErrors).toContainText("cost_price");
    await expect(previewErrors).toContainText("not-a-number");
  } finally {
    await shop.dispose();
  }
});
