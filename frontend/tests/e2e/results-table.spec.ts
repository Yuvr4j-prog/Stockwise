import { expect, test } from "@playwright/test";
import { choosePlanAssumptions, createShop } from "./support";

test("results show the allocation table, totals and purchase slip", async ({ page }) => {
  const shop = await createShop(page);
  try {
    await page.goto("/plans/new");
    await choosePlanAssumptions(page);
    await page.getByRole("button", { name: "Calculate purchase plan" }).click();
    await expect(page).toHaveURL(/\/plans\/\d+$/);
    const table = page.getByRole("table", { name: "Product allocation" });
    await expect(table).toBeVisible();
    await expect(table.getByRole("columnheader", { name: "Buy units" })).toBeVisible();
    await expect(table.getByRole("row")).toHaveCount(6);
    const slip = page.getByLabel("Purchase slip");
    await expect(slip).toBeVisible();
    await expect(slip).toContainText("Total spend");
    await expect(slip).toContainText("Budget remaining");
    await expect(slip).toContainText("Expected profit");
    await expect(page.getByText("Recommendations are estimates based on past sales, not guarantees.")).toBeVisible();
  } finally {
    await shop.dispose();
  }
});
