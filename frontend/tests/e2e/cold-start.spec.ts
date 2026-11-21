import { expect, test } from "@playwright/test";
import { createShop } from "./support";

test("login explains a sleeping backend and retries its health check", async ({ page }) => {
  let checks = 0;
  await page.route("**/api/v1/health", async (route) => {
    checks += 1;
    if (checks === 1) await route.fulfill({ status: 504, body: "Gateway timeout" });
    else await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", max_upload_bytes: 4 * 1024 * 1024 }) });
  });
  await page.route("**/api/v1/health/db", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", database: "ok" }) });
  });

  await page.goto("/login");
  await expect(page.getByRole("status")).toContainText("The server is waking up. This can take up to a minute.");
  await expect(page.getByRole("status")).toHaveCount(0, { timeout: 10_000 });
  expect(checks).toBeGreaterThanOrEqual(2);
});

test("an authenticated read retries after a transient proxy timeout", async ({ page }) => {
  const shop = await createShop(page);
  let reads = 0;
  await page.route("**/api/v1/health", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", max_upload_bytes: 4 * 1024 * 1024 }) });
  });
  await page.route("**/api/v1/health/db", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", database: "ok" }) });
  });
  await page.route("**/api/v1/auth/me", async (route) => {
    reads += 1;
    if (reads === 1) await route.fulfill({ status: 504, body: "Gateway timeout" });
    else await route.continue();
  });

  try {
    await page.goto("/products");
    await expect(page.getByText("The server is waking up. This can take up to a minute.")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Product ledger" })).toBeVisible();
    expect(reads).toBe(2);
  } finally {
    await shop.dispose();
  }
});

test("same-origin proxy preserves signup cookies and authenticated access", async ({ page }) => {
  const email = `proxy-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password").fill("Ledger-proxy-51");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/products$/);
  await expect(page.getByRole("heading", { name: "Product ledger" })).toBeVisible();

  const cookies = await page.context().cookies();
  const session = cookies.find((cookie) => cookie.name === "stockwise_session");
  const csrf = cookies.find((cookie) => cookie.name === "stockwise_csrf");
  expect(session?.httpOnly).toBe(true);
  expect(csrf?.httpOnly).toBe(false);

  await page.reload();
  await expect(page.getByRole("heading", { name: "Product ledger" })).toBeVisible();
  await expect(page.locator(".account-email")).toHaveText(email);
});
