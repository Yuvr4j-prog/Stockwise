export type Seller = { id: number; email: string };

export type Product = {
  id: number;
  sku: string;
  name: string;
  cost_price: string;
  profit_per_unit: string;
  min_order_qty: number;
  pack_size: number;
  forecast_override: string | null;
  notes: string | null;
};

export type SalesWeek = {
  week_start: string;
  units_sold: number;
  stockout_flag: boolean;
};

export type Forecast = {
  product_id: number;
  sku: string;
  name: string;
  forecast: number;
  base_forecast: number;
  method_used: string;
  confidence: "low" | "medium" | "high" | string;
  mae: number | null;
  override_applied: boolean;
  history: SalesWeek[];
};

export type PlanItem = {
  sku: string;
  quantity: number;
  spend: number;
  expected_profit: number;
  reason: string;
  forecast: number;
};

export type Plan = {
  id: number;
  created_at: string;
  budget: string;
  risk_mode: "safe" | "balanced" | "aggressive";
  total_spent: number;
  unspent_budget: number;
  total_profit: number;
  roi: number;
  greedy_profit: number;
  greedy_quantities: Record<string, number>;
  forecasts: Forecast[];
  items: PlanItem[];
  status: string;
  inputs?: {
    budget: string;
    risk_mode: string;
    storage_limit: number | null;
    forecast_method: string;
    window: number;
    alpha: number;
  };
};

export type SavedPlan = {
  id: number;
  created_at: string;
  budget: string;
  risk_mode: string;
  total_spent: number;
  total_profit: number;
  roi: number;
};

export type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
};
