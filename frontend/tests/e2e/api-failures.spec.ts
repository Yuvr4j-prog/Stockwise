import { expect, test } from "@playwright/test";

for (const status of [404, 502, 504]) {
  test(`login identifies an API proxy failure with HTTP ${status}`, async ({ page }) => {
    await page.route("**/api/v1/health", (route) => route.fulfill({
      status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }),
    }));
    await page.route("**/api/v1/health/db", (route) => route.fulfill({
      status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }),
    }));
    await page.route("**/api/v1/auth/csrf", (route) => route.fulfill({ status, body: "Proxy failure" }));
    await page.goto("/login");
    await page.getByLabel("Email address").fill("seller@example.com");
    await page.getByLabel("Password").fill("correct-password");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByRole("alert")).toHaveText(
      `The website could not reach the API (HTTP ${status}). Check the deployment and try again.`,
    );
  });
}

test("login reports invalid credentials separately", async ({ page }) => {
  await page.route("**/api/v1/health", (route) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }),
  }));
  await page.route("**/api/v1/health/db", (route) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", database: "ok" }),
  }));
  await page.route("**/api/v1/auth/csrf", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    headers: { "set-cookie": "stockwise_csrf=test-token; Path=/; SameSite=Lax; Secure" },
    body: JSON.stringify({ csrf_token: "test-token" }),
  }));
  await page.route("**/api/v1/auth/login", (route) => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "invalid_credentials", message: "Email or password is incorrect", details: null } }),
  }));

  await page.goto("/login");
  await page.getByLabel("Email address").fill("seller@example.com");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("alert")).toHaveText("Email or password is incorrect.");
});

test("login reports a sign-in request that does not answer", async ({ page }) => {
  await page.route("**/api/v1/health", (route) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }),
  }));
  await page.route("**/api/v1/health/db", (route) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", database: "ok" }),
  }));
  await page.route("**/api/v1/auth/csrf", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    headers: { "set-cookie": "stockwise_csrf=test-token; Path=/; SameSite=Lax; Secure" },
    body: JSON.stringify({ csrf_token: "test-token" }),
  }));
  await page.route("**/api/v1/auth/login", (route) => route.abort("failed"));

  await page.goto("/login");
  await page.getByLabel("Email address").fill("seller@example.com");
  await page.getByLabel("Password").fill("correct-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("alert")).toHaveText("The API is still starting. Leave this page open and try again in a few minutes.");
});
