import { expect, request, type APIRequestContext, type Page } from "@playwright/test";

const apiOrigin = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const weeks = ["2026-W44", "2026-W45", "2026-W46", "2026-W47"];

export const shopRows = [
  { sku: "RICE-5", name: "Basmati Rice 5 kg", cost: 310, profit: 65, sales: [14, 18, 16, 21] },
  { sku: "OIL-1", name: "Sunflower Oil 1 L", cost: 118, profit: 22, sales: [22, 28, 25, 31] },
  { sku: "SOAP-125", name: "Bath Soap 125 g", cost: 32, profit: 11, sales: [35, 33, 38, 40] },
  { sku: "TEA-250", name: "CTC Tea 250 g", cost: 96, profit: 19, sales: [15, 17, 13, 20] },
  { sku: "BIS-100", name: "Glucose Biscuits 100 g", cost: 8, profit: 3, sales: [64, 58, 71, 68] },
] as const;

export type ShopSession = {
  email: string;
  api: APIRequestContext;
  products: { id: number; sku: string; name: string }[];
  dispose: () => Promise<void>;
};

export async function createShop(page: Page): Promise<ShopSession> {
  const api = await request.newContext({ baseURL: apiOrigin });
  const csrfResponse = await api.get("/api/v1/auth/csrf");
  if (!csrfResponse.ok()) throw new Error(await csrfResponse.text());
  const csrf = (await csrfResponse.json() as { csrf_token: string }).csrf_token;
  const headers = { "X-CSRF-Token": csrf };
  const email = `market-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`;
  const signup = await api.post("/api/v1/auth/signup", { data: { email, password: "Ledger-test-42" }, headers });
  if (signup.status() !== 201) throw new Error(await signup.text());

  const weekColumns = weeks.map((week) => `,${week}`).join("");
  const rows = shopRows.map((product) => [
    product.sku,
    product.name,
    product.cost,
    product.profit,
    ...product.sales,
  ].join(",")).join("\n");
  const csv = `sku,name,cost_price,profit_per_unit${weekColumns}\n${rows}\n`;
  const imported = await api.post("/api/v1/uploads/commit", {
    headers,
    multipart: {
      file: { name: "weekly-sales.csv", mimeType: "text/csv", buffer: Buffer.from(csv) },
    },
  });
  if (imported.status() !== 201) throw new Error(await imported.text());
  const productResponse = await api.get("/api/v1/products");
  if (!productResponse.ok()) throw new Error(await productResponse.text());
  const productRows = await productResponse.json() as { id: number; sku: string; name: string }[];

  const state = await api.storageState();
  await page.context().addCookies(state.cookies);

  return {
    email,
    api,
    products: productRows,
    dispose: () => api.dispose(),
  };
}

export async function choosePlanAssumptions(page: Page) {
  await page.getByLabel("Purchase budget").fill("12000");
  await page.getByRole("button", { name: /Balanced/ }).click();
  await page.getByLabel("Forecast method").selectOption("moving_average");
  await page.getByLabel("Moving-average weeks").fill("3");
  await page.getByLabel("Storage limit (units)").fill("120");
}

export async function expectLoadedProductLedger(page: Page) {
  await page.goto("/products");
  await expect(page.getByRole("heading", { name: "Product ledger", level: 1 })).toBeVisible();
  await expect(page.getByLabel("Product RICE-5")).toHaveValue("Basmati Rice 5 kg");
}
