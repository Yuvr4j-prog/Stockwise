import { expect, test } from "@playwright/test";
import { choosePlanAssumptions, createShop } from "./support";

test("plan builder applies forecast settings, risk and product constraints", async ({ page }) => {
  const shop = await createShop(page);
  try {
    await page.goto("/plans/new");
    await expect(page.getByRole("heading", { name: "Build a purchase plan", level: 1 })).toBeVisible();
    await expect(page.getByText("Basmati Rice 5 kg")).toBeVisible();
    await choosePlanAssumptions(page);
    await page.getByRole("button", { name: /Aggressive/ }).click();
    await expect(page.getByRole("button", { name: /Aggressive/ })).toHaveAttribute("aria-pressed", "true");
    await page.getByLabel("Order rule RICE-5").selectOption("include");
    await page.getByLabel("Order rule BIS-100").selectOption("exclude");
    await page.getByRole("button", { name: "Calculate purchase plan" }).click();
    await expect(page).toHaveURL(/\/plans\/\d+$/);
    await expect(page.getByRole("heading", { name: "Purchase recommendation" })).toBeVisible();
    await expect(page.getByLabel("Purchase slip")).toBeVisible();
  } finally {
    await shop.dispose();
  }
});
