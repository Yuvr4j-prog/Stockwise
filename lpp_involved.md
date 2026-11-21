# Linear programming notes by stage

## Stage 1: data model and migration

No LPP involved. This stage stores product costs, margins, sales history and future plan inputs that the optimizer consumes.

## Stage 1: forecasting

No LPP involved. Forecasts produce product demand caps consumed by the optimizer; stockout observations are lower bounds used to keep the forecast from falling below observed censored sales.

## Stage 1: CSV/XLSX import

No LPP involved. Import validation produces historical sales and product cost/margin inputs consumed by forecasting and the optimizer.

## Stage 1: optimizer

Let `i` index products. Let `x_i` be the number of whole units ordered, `c_i` the unit cost, `p_i` the unit profit, `d_i` the forecast demand, `m_i` the required minimum, and `b` the budget.

\[
\max \sum_i p_i x_i
\]
subject to
\[
\sum_i c_i x_i \le b,\qquad m_i \le x_i \le d_i,\qquad x_i\in\mathbb Z_{\ge0}.
\]

In plain language: choose whole-unit buy quantities to maximize expected profit, without spending over budget or ordering below mandatory minimums or above expected demand.

### Mapping to code

- `stockwise/optimizer.py::solve_plan` validates inputs, constructs risk-adjusted/overridden demand caps and converts bounds into pack-count variables.
- Objective coefficients are `-p_i * pack_size_i` in the SciPy minimization call; this maximizes the corresponding profit.
- Budget row in the sparse `LinearConstraint` is `c_i * pack_size_i`, upper bound `budget`.
- `Bounds` contains integer pack-count lower bounds and floored demand upper bounds. `integrality=np.ones(n)` marks every variable integer.
- Optional storage adds `sum(pack_size_i * y_i) <= storage_limit`. `y_i` is pack count, so `x_i=pack_size_i*y_i`.
- A forced include raises its lower bound to at least one pack (or the explicit minimum); forced exclude sets its upper bound to zero. Conflicts and infeasible demand/budget/storage are returned as `InfeasiblePlan`.
- `demand_scale` is the risk multiplier: Safe `0.80`, Balanced `1.00`, Aggressive `1.15`; an explicit forecast override replaces the product forecast before scaling. The module accepts these numeric scales, while a later API maps the named modes.
- Products with optional nonpositive margin have upper bound zero. A required minimum for a nonpositive-margin item is declared infeasible. Zero-cost positive-margin products remain bounded by demand and storage.

This is an **ILP** (also within the broad MILP class, with no continuous decision variables): the objective and constraints are linear, while order quantities must be whole units/whole packs. Integrality matters because the seller cannot buy fractional units; relaxing integrality could report a cheaper partial item and the wrong recommendation.

### Edge cases

- Negative/NaN/infinite budgets, negative quantities, invalid pack sizes and duplicate SKUs fail input validation.
- Inconsistent bounds or mandatory items exceeding budget/storage produce a readable infeasibility error. Bounds are never silently relaxed.
- No products returns a zero plan. Budget too small yields zero optional units and the full amount unspent. Zero demand has a zero cap. Negative-margin optional products are omitted.
- Multiple optima can exist; SciPy/HiGHS selects an optimum. Greedy ties are broken by SKU. No unbounded objective is possible because each product has a finite demand cap.

### Worked example

Three one-pack products have one-unit demand caps and no minimums or storage cap:

| SKU | Cost | Profit | Demand cap | Profit per rupee |
|---|---:|---:|---:|---:|
| A | ₹10 | ₹60 | 1 | 6.00 |
| B | ₹6 | ₹33 | 1 | 5.50 |
| C | ₹6 | ₹33 | 1 | 5.50 |

Budget is ₹12. The feasible useful choices are none (₹0), A (₹10, profit ₹60), B (₹6, profit ₹33), C (₹6, profit ₹33), and B+C (₹12, profit ₹66). Thus the exact result is `A=0, B=1, C=1`, spend ₹12, profit ₹66, ROI 5.5. Greedy ranks A first by profit per rupee and buys it, leaving ₹2, so its profit is ₹60. It is suboptimal by ₹6. The test suite asserts this solver result when executable.

### Greedy comparison

Greedy sorts by `profit/cost` descending (zero-cost positive-margin items rank first), then SKU; it purchases each ranked product to its cap while budget/storage permits. It is fast and understandable but ignores combinations and indivisible costs, as the example shows. SciPy MILP finds the best feasible integer combination.

## Later stages (not built)

FastAPI/auth and UI consume the same forecast/optimization inputs and outputs but add no distinct LPP. The Docker/seed/docs stage likewise adds no new formulation. These stages have not been started.
